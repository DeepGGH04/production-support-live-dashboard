import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="Support Ops Dashboard", page_icon="📊",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
  #MainMenu,footer,header{visibility:hidden}
  .block-container{padding:1.2rem 2rem 2rem!important;max-width:100%!important}
  .stApp{background:#F4F3EF!important}
  div[data-testid="stTabs"] button {font-size:13px!important;font-weight:600!important;}
</style>""", unsafe_allow_html=True)

try:
    JIRA_BASE  = st.secrets["JIRA_BASE_URL"].rstrip("/")
    JIRA_EMAIL = st.secrets["JIRA_EMAIL"]
    JIRA_TOKEN = st.secrets["JIRA_API_TOKEN"]
except:
    JIRA_BASE  = os.getenv("JIRA_BASE_URL","").rstrip("/")
    JIRA_EMAIL = os.getenv("JIRA_EMAIL","")
    JIRA_TOKEN = os.getenv("JIRA_API_TOKEN","")

PROJECT = '"GGH Production"'
AUTH    = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
HEADERS = {"Accept":"application/json"}
EXCL = ('EMPTY,"Absorb Support (INC)","New Implify/dialer Enhancements (INC)",'
        '"Enhancements (INC)","Report a system problem","Change Order","New Launch","File Ingestion (INC)","SOC incident (INC)",'
        '"Adhoc File Pickup (INC)","8X8 Access (INC)","Access Modification (INC)",'
        '"Request access (INC)","Revoke access (INC)","Onboard New CBO (INC)"')
NOISE  = 'AND summary !~ "Daily checkout" AND summary !~ "IMPLIFY Training" AND summary !~ "Grafana"'
SMAP   = {"Work InProgress":"Work In Progress","Work in progress":"Work In Progress","TODO":"To Do"}

EST = ZoneInfo("America/New_York")

def sow():
    t=datetime.now(EST); return (t-timedelta(days=t.weekday())).strftime("%Y-%m-%d 00:00")
def som():
    return datetime.now(EST).strftime("%Y-%m-01 00:00")
def dow(n):
    """Start of day N days ago in EST"""
    t=datetime.now(EST)-timedelta(days=n)
    return t.strftime("%Y-%m-%d 00:00")

def q_active():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY {NOISE}'
def q_monday():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY AND createdDate<="{sow()}" {NOISE}'
def q_created_today():
    today=datetime.now(EST).strftime("%Y-%m-%d")
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND created>="{today} 00:00" {NOISE}'
def q_res_week():
    return f'project={PROJECT} AND resolved>="{sow()}" AND "Request Type" NOT IN ({EXCL}) AND issue>INC-9800 {NOISE}'
def q_res_month():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution!=EMPTY AND resolved>="{som()}" AND issue>INC-9800 {NOISE}'
def q_created_last30():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND created>="{dow(29)}" AND issue>INC-9800 {NOISE}'
def q_resolved_last30():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolved>="{dow(29)}" AND issue>INC-9800 {NOISE}'

def jql_fetch(jql, limit=500):
    url=f"{JIRA_BASE}/rest/api/3/search/jql"
    flds="summary,status,created,updated,issuetype,priority,resolutiondate,resolution,customfield_10010,assignee"
    issues,token=[],None
    while len(issues)<limit:
        p={"jql":jql,"fields":flds,"maxResults":min(100,limit-len(issues))}
        if token: p["nextPageToken"]=token
        r=requests.get(url,auth=AUTH,headers=HEADERS,params=p); r.raise_for_status()
        d=r.json(); batch=d.get("issues",[])
        issues+=batch; token=d.get("nextPageToken")
        if not batch or not token: break
    return issues

def sname(i):
    raw=i.get("fields",{}).get("status",{}).get("name","?"); return SMAP.get(raw,raw)
def age(i):
    c=i.get("fields",{}).get("created","")
    return (datetime.now(EST)-datetime.fromisoformat(c.replace("Z","+00:00")).astimezone(EST)).days if c else 0
def res_date(i):
    r=i.get("fields",{}).get("resolutiondate","")
    return datetime.fromisoformat(r.replace("Z","+00:00")).astimezone(EST) if r else None
def fdate(iso):
    try: return datetime.fromisoformat(iso.replace("Z","+00:00")).astimezone(EST).strftime("%d %b") if iso else ""
    except: return ""
def get_rt(i):
    f=i.get("fields",{}).get("customfield_10010") or {}
    n=f.get("requestType",{}).get("name","").strip() if isinstance(f,dict) else ""
    return n if n and n.lower() not in ("none","other","") else None
def get_assignee(i):
    a=i.get("fields",{}).get("assignee") or {}
    return a.get("displayName","Unassigned")
def resb(issues):
    c={}
    for i in issues:
        r=(i.get("fields",{}).get("resolution") or {}).get("name","") or i.get("fields",{}).get("status",{}).get("name","Other")
        c[r]=c.get(r,0)+1
    return c

@st.cache_data(ttl=0, show_spinner=False)
def load_data():
    qs={
        "active":       (q_active(),        500),
        "monday":       (q_monday(),        500),
        "res_week":     (q_res_week(),      500),
        "res_month":    (q_res_month(),     500),
        "bugs":         (f'project={PROJECT} AND status=PROD_BUG AND resolution=EMPTY', 50),
        "today":        (q_created_today(), 100),
        "created_30":   (q_created_last30(),1000),
        "resolved_30":  (q_resolved_last30(),1000),
    }
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut={k:ex.submit(jql_fetch,q,lim) for k,(q,lim) in qs.items()}
        return {k:fut[k].result() for k in fut}

JIRA_URL = "https://groundgamehealth.atlassian.net/browse/"
now_str  = datetime.now(EST).strftime("%d %b %Y, %H:%M EST")
CARD = "background:white;border-radius:12px;border:1px solid #e8e6e0;padding:20px 24px;"
BG   = dict(paper_bgcolor="white", plot_bgcolor="white",
            margin=dict(t=44,b=10,l=10,r=24), height=320,
            font=dict(family="sans-serif",size=12,color="#475569"))

# ── Header ────────────────────────────────────────────────
st.markdown(f"""
<div style="background:#0F1F3D;border-radius:12px;padding:0 28px;
            display:flex;align-items:center;justify-content:space-between;
            height:80px;margin-bottom:16px">
  <div>
    <div style="font-size:22px;font-weight:700;color:white;line-height:1.2">
      Production Support Jira Board — Live Dashboard
    </div>
    <div style="font-size:12px;color:#94A3B8;margin-top:4px">Last updated: {now_str}</div>
  </div>
  <div style="background:#0D9E75;color:white;border-radius:20px;
              padding:7px 18px;font-size:12px;font-weight:700;letter-spacing:.04em">
    <span style="color:#ff4444">●</span> LIVE · GROUNDGAMEHEALTH
  </div>
</div>""", unsafe_allow_html=True)

# ── Deep Dive nav button (native Streamlit) ──────────────
_, nav_col = st.columns([9, 1])
with nav_col:
    if st.button("🔍 Deep Dive", use_container_width=True):
        st.switch_page("pages/2_Deep_Dive.py")
st.markdown("""
<style>
  /* Style the Deep Dive button to look like a nav pill */
  div[data-testid="stButton"] > button {
      background: #1E3A6E !important;
      color: white !important;
      border: 1px solid rgba(255,255,255,0.2) !important;
      border-radius: 8px !important;
      font-size: 12px !important;
      font-weight: 600 !important;
      margin-top: -60px !important;
  }
  div[data-testid="stButton"] > button:hover {
      background: #2a4f96 !important;
  }
</style>""", unsafe_allow_html=True)

# ── Load ──────────────────────────────────────────────────
with st.spinner("Loading live data from Jira…"):
    try: data=load_data()
    except Exception as e: st.error(f"⚠️ {e}"); st.stop()

active       = data["active"]
monday       = data["monday"]
res_week     = data["res_week"]
res_mon      = data["res_month"]
bugs         = data["bugs"]
created_30   = data["created_30"]
resolved_30  = data["resolved_30"]
created_today= len(data["today"])

t_now        = datetime.now(EST)
month_start  = t_now.replace(day=1,hour=0,minute=0,second=0,microsecond=0,tzinfo=EST)
days_elapsed = max((t_now-month_start).days,1)
weeks_elapsed= max(days_elapsed/7,1)
avg_weekly   = round(len(res_mon)/weeks_elapsed)
net          = len(active)-len(monday)
ns           = "+" if net>=0 else ""
nc           = "#C0392B" if net>0 else "#27700F"
aged         = sorted(active,key=lambda i:-age(i))
oldest       = aged[0] if aged else None
oa           = age(oldest) if oldest else 0
ok           = oldest["key"] if oldest else "N/A"

# ── Avg time to resolution (from resolved_30) ────────────
def avg_resolution_days(issues):
    days_list=[]
    for i in issues:
        c=i.get("fields",{}).get("created","")
        rd=i.get("fields",{}).get("resolutiondate","")
        if c and rd:
            created_dt=datetime.fromisoformat(c.replace("Z","+00:00")).astimezone(EST)
            resolved_dt=datetime.fromisoformat(rd.replace("Z","+00:00")).astimezone(EST)
            days_list.append((resolved_dt-created_dt).days)
    return round(sum(days_list)/len(days_list)) if days_list else 0

avg_res_days = avg_resolution_days(resolved_30)

# ── Daily trend data (last 30 days) ──────────────────────
def daily_counts(issues, date_field="created"):
    counts={}
    for i in issues:
        raw=i.get("fields",{}).get(date_field,"") or i.get("fields",{}).get("resolutiondate","")
        if raw:
            d=datetime.fromisoformat(raw.replace("Z","+00:00")).astimezone(EST).strftime("%Y-%m-%d")
            counts[d]=counts.get(d,0)+1
    return counts

created_daily  = daily_counts(created_30,"created")
resolved_daily = daily_counts(resolved_30,"resolutiondate")
all_days       = sorted(set(list(created_daily.keys())+list(resolved_daily.keys())))
df_trend       = pd.DataFrame({
    "Date":     all_days,
    "Created":  [created_daily.get(d,0) for d in all_days],
    "Resolved": [resolved_daily.get(d,0) for d in all_days],
})

# ── Assignee breakdown ────────────────────────────────────
assignee_counts={}
for i in active:
    a=get_assignee(i)
    assignee_counts[a]=assignee_counts.get(a,0)+1

assignee_res={}
for i in res_week:
    a=get_assignee(i)
    assignee_res[a]=assignee_res.get(a,0)+1

# ── KPI row ───────────────────────────────────────────────
st.markdown("<p style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#888;margin:0 0 10px'>KEY METRICS AT A GLANCE</p>", unsafe_allow_html=True)

k1,k2,k3,k4,k5,k6 = st.columns(6)
kpis = [
    (k1,"Active Tickets",       str(len(active)),
         f'<span style="color:#C0392B;font-weight:600">+{created_today} Today</span>&nbsp;·&nbsp;<span style="color:{nc};font-weight:600">{ns}{net}</span> Since Last Week'),
    (k2,"Resolved This Week",   str(len(res_week)),  "Tickets Closed This Week"),
    (k3,"Avg Resolved / Week",  str(avg_weekly),     "Weekly Avg This Month"),
    (k4,"Resolved This Month",  str(len(res_mon)),   "Across All Request Types"),
    (k5,"Avg Time To Resolve",  f"{avg_res_days}d",  "Last 30 Days"),
    (k6,"Oldest Open Ticket",   f"{oa}d",
         f'<span style="color:#C0392B;font-weight:600">{ok}</span>'),
]
for col,lbl,val,sub in kpis:
    with col:
        st.markdown(f"""<div style="{CARD}">
          <div style="font-size:12px;color:#888;margin-bottom:8px">{lbl}</div>
          <div style="font-size:36px;font-weight:700;color:#1a1a18;line-height:1;margin-bottom:6px">{val}</div>
          <div style="font-size:12px;color:#888">{sub}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ── Insights ─────────────────────────────────────────────
st.markdown("<p style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#888;margin:0 0 10px'>KEY INSIGHTS</p>", unsafe_allow_html=True)
trend="Triage session recommended." if net>5 else "Backlog is stable."
bmsg=f"{len(bugs)} active production bug{'s' if len(bugs)!=1 else ''} in the backlog. Requires sprint commitment." if bugs else "No open production bugs 🎉"
top_assignee=max(assignee_counts,key=assignee_counts.get) if assignee_counts else "N/A"
top_count=assignee_counts.get(top_assignee,0)
unassigned=assignee_counts.get("Unassigned",0)
for col,(bc,tc,title,body) in zip(st.columns(4),[
    ("#EF4444","#991B1B","Backlog Trend",    f"Net {ns}{net} tickets this week — active count is {len(active)}. {trend}"),
    ("#F59E0B","#92400E","Aging Tickets",    f"Oldest open ticket is {oa} days old ({ok}). Review tickets aged over 60 days."),
    ("#3B82F6","#1E40AF","Production Bugs",  bmsg),
    ("#0D9E75","#065F46","Team Load",        f"{top_assignee} has most active tickets ({top_count}). {unassigned} unassigned ticket{'s' if unassigned!=1 else ''} need assignment."),
]):
    with col:
        st.markdown(f"""<div style="background:white;border-left:4px solid {bc};
          border-top:1px solid #e8e6e0;border-right:1px solid #e8e6e0;
          border-bottom:1px solid #e8e6e0;border-radius:0 10px 10px 0;
          padding:14px 18px;min-height:85px">
          <div style="font-size:13px;font-weight:700;color:{tc};margin-bottom:5px">{title}</div>
          <div style="font-size:12px;color:#555;line-height:1.6">{body}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4 = st.tabs([
    "📊  Overview",
    "📈  Trends & Visibility",
    "👤  Team Performance",
    "🐛  Prod Bugs"
])

# ──────────────────────────────────────────────────────────
# TAB 1 — OVERVIEW (existing charts + tables)
# ──────────────────────────────────────────────────────────
with tab1:
    sc={}
    for i in active: s=sname(i); sc[s]=sc.get(s,0)+1
    rc={}
    for i in active:
        v=get_rt(i)
        if v: rc[v]=rc.get(v,0)+1

    c1,c2=st.columns(2)
    with c1:
        fig=go.Figure(go.Pie(labels=list(sc.keys()),values=list(sc.values()),
            hole=0.58,textposition="inside",textinfo="percent",
            marker_colors=["#F59E0B","#9CA3AF","#3B82F6","#EF4444","#0D9E75","#8B5CF6","#14B8A6"]))
        fig.update_layout(**BG,
            title=dict(text="ACTIVE TICKET STATUS",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
            legend=dict(orientation="h",xanchor="center",x=0.5,yanchor="top",y=-0.04,font=dict(size=11)))
        st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})
    with c2:
        df_rt=pd.DataFrame(sorted(rc.items(),key=lambda x:x[1]),columns=["Type","Count"])
        fig2=px.bar(df_rt,x="Count",y="Type",orientation="h",color_discrete_sequence=["#3B82F6"],text="Count")
        fig2.update_traces(textposition="outside",textfont_size=11)
        fig2.update_layout(**BG,
            title=dict(text="ACTIVE BY REQUEST TYPE",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
            xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
            yaxis=dict(showgrid=False,title="",automargin=True))
        st.plotly_chart(fig2,use_container_width=True,config={"displayModeBar":False})

    rb_wk=resb(res_week); rb_mo=resb(res_mon)
    c3,c4=st.columns(2)
    with c3:
        if rb_wk:
            df_wk=pd.DataFrame(sorted(rb_wk.items(),key=lambda x:x[1])[-7:],columns=["Reason","Count"])
            fig3=px.bar(df_wk,x="Count",y="Reason",orientation="h",color_discrete_sequence=["#0D9E75"],text="Count")
            fig3.update_traces(textposition="outside",textfont_size=11)
            fig3.update_layout(**BG,
                title=dict(text=f"RESOLUTION REASONS — THIS WEEK ({len(res_week)} TICKETS)",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
                xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),yaxis=dict(showgrid=False,title=""))
            st.plotly_chart(fig3,use_container_width=True,config={"displayModeBar":False})
        else:
            st.markdown(f"""<div style="{CARD}text-align:center;padding:40px">
              <div style="font-size:11px;color:#888">RESOLUTION REASONS — THIS WEEK</div>
              <div style="font-size:14px;color:#aaa;margin-top:12px">No tickets resolved yet this week</div>
            </div>""", unsafe_allow_html=True)
    with c4:
        if rb_mo:
            df_mo=pd.DataFrame(sorted(rb_mo.items(),key=lambda x:x[1])[-8:],columns=["Reason","Count"])
            fig4=px.bar(df_mo,x="Count",y="Reason",orientation="h",color_discrete_sequence=["#7C3AED"],text="Count")
            fig4.update_traces(textposition="outside",textfont_size=11)
            fig4.update_layout(**BG,
                title=dict(text=f"RESOLUTION REASONS — THIS MONTH ({len(res_mon)} TICKETS)",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
                xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),yaxis=dict(showgrid=False,title=""))
            st.plotly_chart(fig4,use_container_width=True,config={"displayModeBar":False})

    st.markdown("<hr style='border:none;border-top:1px solid #e8e6e0;margin:8px 0 14px'>",unsafe_allow_html=True)
    t1,t2=st.columns(2)
    with t1:
        st.markdown("<p style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#1a1a18;margin:0 0 8px'>AGING BACKLOG — OLDEST OPEN TICKETS</p>", unsafe_allow_html=True)
        if aged:
            st.dataframe(pd.DataFrame([{
                "Ticket":f"{JIRA_URL}{i['key']}","Summary":i.get("fields",{}).get("summary","")[:50],
                "Age (d)":age(i),"Status":sname(i)} for i in aged[:7]]),
                use_container_width=True,hide_index=True,
                column_config={
                    "Ticket":st.column_config.LinkColumn("Ticket",width="small",display_text=r"(INC-\d+)"),
                    "Age (d)":st.column_config.NumberColumn(width="small")})
    with t2:
        st.markdown(f"<p style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#1a1a18;margin:0 0 8px'>OPEN PRODUCTION BUGS ({len(bugs)})</p>", unsafe_allow_html=True)
        if bugs:
            st.dataframe(pd.DataFrame([{
                "Ticket":f"{JIRA_URL}{b['key']}","Summary":b.get("fields",{}).get("summary","")[:48],
                "Created":fdate(b.get("fields",{}).get("created",""))} for b in bugs[:10]]),
                use_container_width=True,hide_index=True,
                column_config={"Ticket":st.column_config.LinkColumn("Ticket",width="small",display_text=r"(INC-\d+)")})
        else:
            st.success("No open production bugs 🎉")

# ──────────────────────────────────────────────────────────
# TAB 2 — TRENDS & VISIBILITY
# ──────────────────────────────────────────────────────────
with tab2:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # 30-day backlog trend
    # Add 7-day rolling avg
    df_trend["Created_MA7"]  = df_trend["Created"].rolling(7,min_periods=1).mean().round(1)
    df_trend["Resolved_MA7"] = df_trend["Resolved"].rolling(7,min_periods=1).mean().round(1)

    fig_trend=go.Figure()
    fig_trend.add_trace(go.Bar(
        x=df_trend["Date"],y=df_trend["Created"],
        name="Created",marker_color="#FCA5A5",opacity=0.6,
        hovertemplate="%{x}<br><b>Created: %{y}</b><extra></extra>"))
    fig_trend.add_trace(go.Bar(
        x=df_trend["Date"],y=df_trend["Resolved"],
        name="Resolved",marker_color="#6EE7B7",opacity=0.6,
        hovertemplate="%{x}<br><b>Resolved: %{y}</b><extra></extra>"))
    fig_trend.add_trace(go.Scatter(
        x=df_trend["Date"],y=df_trend["Created_MA7"],
        name="Created 7d avg",mode="lines",
        line=dict(color="#EF4444",width=2.5,dash="dot"),
        hovertemplate="%{x}<br>7d avg created: %{y}<extra></extra>"))
    fig_trend.add_trace(go.Scatter(
        x=df_trend["Date"],y=df_trend["Resolved_MA7"],
        name="Resolved 7d avg",mode="lines",
        line=dict(color="#0D9E75",width=2.5,dash="dot"),
        hovertemplate="%{x}<br>7d avg resolved: %{y}<extra></extra>"))
    fig_trend.update_layout(
        paper_bgcolor="white",plot_bgcolor="white",
        barmode="group",height=320,margin=dict(t=44,b=20,l=10,r=10),
        font=dict(family="sans-serif",size=12,color="#475569"),
        title=dict(text="DAILY TICKET CREATION VS CLOSURE — LAST 30 DAYS",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
        legend=dict(orientation="h",x=1,xanchor="right",y=1.12,font=dict(size=10)),
        xaxis=dict(showgrid=False,tickangle=-30,tickfont=dict(size=10)),
        yaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="white",bordercolor="#e8e6e0",font_size=12))
    st.plotly_chart(fig_trend,use_container_width=True,config={"displayModeBar":False})

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
    c5,c6=st.columns(2)

    # Weekly creation heatmap by day of week
    with c5:
        dow_map={0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
        dow_counts={v:0 for v in dow_map.values()}
        for i in created_30:
            c=i.get("fields",{}).get("created","")
            if c:
                d=datetime.fromisoformat(c.replace("Z","+00:00")).astimezone(EST)
                dow_counts[dow_map[d.weekday()]]=dow_counts.get(dow_map[d.weekday()],0)+1
        days_order=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        fig_dow=px.bar(
            x=days_order,y=[dow_counts[d] for d in days_order],
            color=[dow_counts[d] for d in days_order],
            color_continuous_scale=["#EFF6FF","#3B82F6","#1E40AF"],
            text=[dow_counts[d] for d in days_order])
        fig_dow.update_traces(textposition="outside",textfont_size=11)
        fig_dow.update_layout(
            paper_bgcolor="white",plot_bgcolor="white",
            height=280,margin=dict(t=44,b=10,l=10,r=10),
            font=dict(family="sans-serif",size=12,color="#475569"),
            title=dict(text="TICKETS CREATED BY DAY OF WEEK (30 DAYS)",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
            coloraxis_showscale=False,showlegend=False,
            xaxis=dict(showgrid=False,title=""),
            yaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""))
        st.plotly_chart(fig_dow,use_container_width=True,config={"displayModeBar":False})

    # Avg resolution time by request type
    with c6:
        rt_res_days={}
        rt_res_count={}
        for i in resolved_30:
            rt=get_rt(i)
            c=i.get("fields",{}).get("created","")
            rd=i.get("fields",{}).get("resolutiondate","")
            if rt and c and rd:
                d=(datetime.fromisoformat(rd.replace("Z","+00:00")).astimezone(EST)-
                   datetime.fromisoformat(c.replace("Z","+00:00")).astimezone(EST)).days
                rt_res_days[rt]=rt_res_days.get(rt,0)+d
                rt_res_count[rt]=rt_res_count.get(rt,0)+1
        rt_avg={k:round(rt_res_days[k]/rt_res_count[k]) for k in rt_res_days if rt_res_count[k]>=2}
        if rt_avg:
            df_rtavg=pd.DataFrame(sorted(rt_avg.items(),key=lambda x:x[1]),columns=["Request Type","Avg Days"])
            fig_rtavg=px.bar(df_rtavg,x="Avg Days",y="Request Type",orientation="h",
                             color="Avg Days",color_continuous_scale=["#D1FAE5","#F59E0B","#EF4444"],
                             text="Avg Days")
            fig_rtavg.update_traces(textposition="outside",textfont_size=11)
            fig_rtavg.update_layout(
                paper_bgcolor="white",plot_bgcolor="white",
                height=280,margin=dict(t=44,b=10,l=10,r=10),
                font=dict(family="sans-serif",size=12,color="#475569"),
                title=dict(text="AVG RESOLUTION TIME BY REQUEST TYPE (30 DAYS)",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
                coloraxis_showscale=False,showlegend=False,
                xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title="Days"),
                yaxis=dict(showgrid=False,title="",automargin=True))
            st.plotly_chart(fig_rtavg,use_container_width=True,config={"displayModeBar":False})
        else:
            st.info("Not enough resolved tickets to calculate avg resolution time by type.")

# ──────────────────────────────────────────────────────────
# TAB 3 — TEAM PERFORMANCE
# ──────────────────────────────────────────────────────────
with tab3:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    c7,c8=st.columns(2)

    with c7:
        if assignee_counts:
            df_asgn=pd.DataFrame(sorted(assignee_counts.items(),key=lambda x:x[1]),columns=["Assignee","Active Tickets"])
            total_a = df_asgn["Active Tickets"].sum() or 1
            df_asgn["Pct"] = (df_asgn["Active Tickets"]/total_a*100).round(1)
            fig_asgn=px.bar(df_asgn,x="Active Tickets",y="Assignee",orientation="h",
                            color="Active Tickets",color_continuous_scale=["#BFDBFE","#3B82F6","#1E40AF"],
                            text="Active Tickets",custom_data=["Pct"])
            fig_asgn.update_traces(textposition="outside",textfont_size=11,
                hovertemplate="<b>%{y}</b><br>%{x} active tickets (%{customdata[0]}% of backlog)<extra></extra>")
            fig_asgn.update_layout(
                paper_bgcolor="white",plot_bgcolor="white",
                height=max(320,len(assignee_counts)*32+80),margin=dict(t=44,b=10,l=10,r=10),
                font=dict(family="sans-serif",size=12,color="#475569"),
                title=dict(text="ACTIVE TICKETS BY ASSIGNEE",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
                coloraxis_showscale=False,
                xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
                yaxis=dict(showgrid=False,title="",automargin=True),
                hoverlabel=dict(bgcolor="white",bordercolor="#e8e6e0",font_size=12))
            st.plotly_chart(fig_asgn,use_container_width=True,config={"displayModeBar":False})

    with c8:
        if assignee_res:
            df_ares=pd.DataFrame(sorted(assignee_res.items(),key=lambda x:x[1]),columns=["Assignee","Resolved This Week"])
            fig_ares=px.bar(df_ares,x="Resolved This Week",y="Assignee",orientation="h",
                            color_discrete_sequence=["#0D9E75"],text="Resolved This Week")
            fig_ares.update_traces(textposition="outside",textfont_size=11)
            fig_ares.update_layout(
                paper_bgcolor="white",plot_bgcolor="white",
                height=360,margin=dict(t=44,b=10,l=10,r=10),
                font=dict(family="sans-serif",size=12,color="#475569"),
                title=dict(text="RESOLVED THIS WEEK BY ASSIGNEE",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
                xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
                yaxis=dict(showgrid=False,title="",automargin=True))
            st.plotly_chart(fig_ares,use_container_width=True,config={"displayModeBar":False})
        else:
            st.info("No tickets resolved this week yet.")

    # Unassigned alert + pending review table
    st.markdown("<hr style='border:none;border-top:1px solid #e8e6e0;margin:8px 0 14px'>", unsafe_allow_html=True)
    c9,c10=st.columns(2)
    with c9:
        st.markdown("<p style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#1a1a18;margin:0 0 8px'>UNASSIGNED TICKETS</p>", unsafe_allow_html=True)
        unassigned_tickets=[i for i in active if get_assignee(i)=="Unassigned"]
        if unassigned_tickets:
            st.warning(f"⚠️ {len(unassigned_tickets)} unassigned ticket{'s' if len(unassigned_tickets)!=1 else ''} need assignment")
            st.dataframe(pd.DataFrame([{
                "Ticket":f"{JIRA_URL}{i['key']}",
                "Summary":i.get("fields",{}).get("summary","")[:50],
                "Age (d)":age(i),"Status":sname(i)} for i in unassigned_tickets[:10]]),
                use_container_width=True,hide_index=True,
                column_config={
                    "Ticket":st.column_config.LinkColumn("Ticket",width="small",display_text=r"(INC-\d+)"),
                    "Age (d)":st.column_config.NumberColumn(width="small")})
        else:
            st.success("✅ All tickets are assigned")

    with c10:
        st.markdown("<p style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#1a1a18;margin:0 0 8px'>TOP ASSIGNEES — ACTIVE LOAD</p>", unsafe_allow_html=True)
        rows=[]
        for name,count in sorted(assignee_counts.items(),key=lambda x:-x[1])[:10]:
            resolved_count=assignee_res.get(name,0)
            rows.append({"Assignee":name,"Active":count,"Resolved/Week":resolved_count})
        if rows:
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,
                column_config={
                    "Active":st.column_config.NumberColumn(width="small"),
                    "Resolved/Week":st.column_config.NumberColumn(width="small")})

# ──────────────────────────────────────────────────────────
# TAB 4 — PROD BUGS
# ──────────────────────────────────────────────────────────
with tab4:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    c11,c12=st.columns(2)

    with c11:
        # Bug age distribution
        if bugs:
            bug_ages=[age(b) for b in bugs]
            df_bugs_age=pd.DataFrame({"Ticket":[b["key"] for b in bugs],
                                       "Summary":[b.get("fields",{}).get("summary","")[:35] for b in bugs],
                                       "Age (d)":bug_ages})
            df_bugs_age=df_bugs_age.sort_values("Age (d)",ascending=True)
            colors=["#EF4444" if a>=60 else "#F59E0B" if a>=30 else "#0D9E75" for a in df_bugs_age["Age (d)"]]
            fig_bage=px.bar(df_bugs_age,x="Age (d)",y="Ticket",orientation="h",
                            text="Age (d)",color="Age (d)",
                            color_continuous_scale=["#D1FAE5","#FEF3C7","#FEE2E2"])
            fig_bage.update_traces(textposition="outside",textfont_size=10)
            fig_bage.update_layout(
                paper_bgcolor="white",plot_bgcolor="white",
                height=max(280,len(bugs)*28+60),margin=dict(t=44,b=10,l=10,r=10),
                font=dict(family="sans-serif",size=11,color="#475569"),
                title=dict(text=f"PROD BUG AGE — ALL {len(bugs)} OPEN BUGS",font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
                coloraxis_showscale=False,showlegend=False,
                xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title="Days Open"),
                yaxis=dict(showgrid=False,title="",automargin=True))
            st.plotly_chart(fig_bage,use_container_width=True,config={"displayModeBar":False})

    with c12:
        # Bug open/close trend (last 30 days)
        bugs_opened_daily={}
        bugs_closed_daily={}
        for i in created_30:
            if sname(i)=="PROD_BUG" or (i.get("fields",{}).get("status",{}).get("name","")=="PROD_BUG"):
                c=i.get("fields",{}).get("created","")
                if c:
                    d=datetime.fromisoformat(c.replace("Z","+00:00")).astimezone(EST).strftime("%Y-%m-%d")
                    bugs_opened_daily[d]=bugs_opened_daily.get(d,0)+1
        for i in resolved_30:
            rt=get_rt(i)
            res=(i.get("fields",{}).get("resolution") or {}).get("name","")
            if res=="PROD_BUG":
                rd=i.get("fields",{}).get("resolutiondate","")
                if rd:
                    d=datetime.fromisoformat(rd.replace("Z","+00:00")).astimezone(EST).strftime("%Y-%m-%d")
                    bugs_closed_daily[d]=bugs_closed_daily.get(d,0)+1

        # Full bug table
        st.markdown(f"<p style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#1a1a18;margin:0 0 8px'>ALL OPEN PROD BUGS ({len(bugs)})</p>", unsafe_allow_html=True)
        if bugs:
            st.dataframe(pd.DataFrame([{
                "Ticket":   f"{JIRA_URL}{b['key']}",
                "Summary":  b.get("fields",{}).get("summary","")[:55],
                "Age (d)":  age(b),
                "Status":   sname(b),
                "Created":  fdate(b.get("fields",{}).get("created",""))} for b in sorted(bugs,key=lambda x:-age(x))]),
                use_container_width=True,hide_index=True,
                column_config={
                    "Ticket":   st.column_config.LinkColumn("Ticket",width="small",display_text=r"(INC-\d+)"),
                    "Age (d)":  st.column_config.NumberColumn(width="small")})
        else:
            st.success("No open production bugs 🎉")

st.markdown(f"<p style='text-align:center;font-size:12px;color:#aaa;margin-top:20px;padding-top:16px;border-top:1px solid #e8e6e0'>Support Operations Live Dashboard · groundgamehealth.atlassian.net · {now_str}</p>",unsafe_allow_html=True)