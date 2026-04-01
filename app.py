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
def som():  return datetime.now(EST).strftime("%Y-%m-01 00:00")

def q_active():    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY {NOISE}'
def q_monday():    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY AND createdDate<="{sow()}" {NOISE}'
def q_created_today():
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND created>="{today} 00:00" {NOISE}'
def q_res_week():  return f'project={PROJECT} AND resolved>="{sow()}" AND "Request Type" NOT IN ({EXCL}) AND issue>INC-9800 {NOISE}'
def q_res_month(): return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution!=EMPTY AND resolved>="{som()}" AND issue>INC-9800 {NOISE}'

def jql_fetch(jql,limit=500):
    url=f"{JIRA_BASE}/rest/api/3/search/jql"
    flds="summary,status,created,updated,issuetype,priority,resolutiondate,resolution,customfield_10010"
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
def fdate(iso):
    try: return datetime.fromisoformat(iso.replace("Z","+00:00")).astimezone(EST).strftime("%d %b") if iso else ""
    except: return ""
def get_rt(i):
    f=i.get("fields",{}).get("customfield_10010") or {}
    n=f.get("requestType",{}).get("name","").strip() if isinstance(f,dict) else ""
    return n if n and n.lower() not in ("none","other","") else None
def resb(issues):
    c={}
    for i in issues:
        r=(i.get("fields",{}).get("resolution") or {}).get("name","") or i.get("fields",{}).get("status",{}).get("name","Other")
        c[r]=c.get(r,0)+1
    return c

@st.cache_data(ttl=0,show_spinner=False)
def load_data():
    qs={"active":(q_active(),500),"monday":(q_monday(),500),
        "res_week":(q_res_week(),500),"res_month":(q_res_month(),500),
        "bugs":(f'project={PROJECT} AND status=PROD_BUG AND resolution=EMPTY',20),
        "today":(q_created_today(),100)}
    with ThreadPoolExecutor(max_workers=6) as ex:
        fut={k:ex.submit(jql_fetch,q,lim) for k,(q,lim) in qs.items()}
        return {k:fut[k].result() for k in fut}

JIRA_URL = "https://groundgamehealth.atlassian.net/browse/"
now_str  = datetime.now(EST).strftime("%d %b %Y, %H:%M EST")
CARD = "background:white;border-radius:12px;border:1px solid #e8e6e0;padding:20px 24px;"
BG   = dict(paper_bgcolor="white",plot_bgcolor="white",
            margin=dict(t=44,b=10,l=10,r=24),height=320,
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

# ── Load ──────────────────────────────────────────────────
with st.spinner("Loading live data from Jira…"):
    try: data=load_data()
    except Exception as e: st.error(f"⚠️ {e}"); st.stop()

active=data["active"]; monday=data["monday"]
res_week=data["res_week"]; res_mon=data["res_month"]; bugs=data["bugs"]
created_today=len(data["today"])
t_now = datetime.now(EST)
month_start = t_now.replace(day=1,hour=0,minute=0,second=0,microsecond=0,tzinfo=EST)
days_elapsed = max((t_now-month_start).days,1)
weeks_elapsed = max(days_elapsed/7,1)
avg_weekly_resolved = round(len(res_mon)/weeks_elapsed)
net=len(active)-len(monday); ns="+" if net>=0 else ""; nc="#C0392B" if net>0 else "#27700F"
aged=sorted(active,key=lambda i:-age(i)); oldest=aged[0] if aged else None
oa=age(oldest) if oldest else 0; ok=oldest["key"] if oldest else "N/A"

# ── KPI cards (5 columns) ─────────────────────────────────
st.markdown("<p style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#888;margin:0 0 10px'>KEY METRICS AT A GLANCE</p>", unsafe_allow_html=True)

k1,k2,k3,k4,k5 = st.columns(5)

kpis = [
    (k1, "Active Tickets",          str(len(active)),
         f'<span style="color:#C0392B;font-weight:600">+{created_today} Today</span> &nbsp;·&nbsp; <span style="color:{nc};font-weight:600">{ns}{net}</span> Since Last Week'),
    (k2, "Resolved This Week",      str(len(res_week)),
         "Tickets Closed This Week"),
    (k3, "Avg Resolved / Week",     str(avg_weekly_resolved),
         "Weekly Avg This Month"),
    (k4, "Resolved This Month",     str(len(res_mon)),
         "Across All Request Types"),
    (k5, "Oldest Open Ticket",      f"{oa}d",
         f'<span style="color:#C0392B;font-weight:600">{ok}</span>'),
]

for col,lbl,val,sub in kpis:
    with col:
        st.markdown(f"""<div style="{CARD}">
          <div style="font-size:13px;color:#888;margin-bottom:8px">{lbl}</div>
          <div style="font-size:40px;font-weight:700;color:#1a1a18;line-height:1;margin-bottom:6px">{val}</div>
          <div style="font-size:13px;color:#888">{sub}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ── Insights ─────────────────────────────────────────────
st.markdown("<p style='font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#888;margin:0 0 10px'>KEY INSIGHTS</p>", unsafe_allow_html=True)
trend="Triage session recommended." if net>5 else "Backlog is stable."
bmsg=f"{len(bugs)} active production bug{'s' if len(bugs)!=1 else ''} in the backlog. Requires sprint commitment." if bugs else "No open production bugs 🎉"
for col,(bc,tc,title,body) in zip(st.columns(3),[
    ("#EF4444","#991B1B","Backlog Trend",  f"Net {ns}{net} tickets this week — active count is {len(active)}. {trend}"),
    ("#F59E0B","#92400E","Aging Tickets",  f"Oldest open ticket is {oa} days old ({ok}). Review tickets aged over 60 days."),
    ("#3B82F6","#1E40AF","Production Bugs",bmsg)]):
    with col:
        st.markdown(f"""<div style="background:white;border-left:4px solid {bc};
          border-top:1px solid #e8e6e0;border-right:1px solid #e8e6e0;
          border-bottom:1px solid #e8e6e0;border-radius:0 10px 10px 0;
          padding:16px 18px;min-height:85px">
          <div style="font-size:14px;font-weight:700;color:{tc};margin-bottom:5px">{title}</div>
          <div style="font-size:13px;color:#555;line-height:1.6">{body}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ── Charts row 1 ──────────────────────────────────────────
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
        title=dict(text="ACTIVE TICKET STATUS",font=dict(size=11,color="#1a1a18",family="sans-serif"),
                   x=0,xanchor="left",pad=dict(l=4,t=4)),
        legend=dict(orientation="h",xanchor="center",x=0.5,yanchor="top",y=-0.04,font=dict(size=11)))
    st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})

with c2:
    df_rt=pd.DataFrame(sorted(rc.items(),key=lambda x:x[1]),columns=["Type","Count"])
    fig2=px.bar(df_rt,x="Count",y="Type",orientation="h",
                color_discrete_sequence=["#3B82F6"],text="Count")
    fig2.update_traces(textposition="outside",textfont_size=11)
    fig2.update_layout(**BG,
        title=dict(text="ACTIVE BY REQUEST TYPE",font=dict(size=11,color="#1a1a18",family="sans-serif"),
                   x=0,xanchor="left",pad=dict(l=4,t=4)),
        xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
        yaxis=dict(showgrid=False,title="",automargin=True))
    st.plotly_chart(fig2,use_container_width=True,config={"displayModeBar":False})

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── Charts row 2 ──────────────────────────────────────────
rb_wk=resb(res_week); rb_mo=resb(res_mon)
c3,c4=st.columns(2)

with c3:
    if rb_wk:
        df_wk=pd.DataFrame(sorted(rb_wk.items(),key=lambda x:x[1])[-7:],columns=["Reason","Count"])
        fig3=px.bar(df_wk,x="Count",y="Reason",orientation="h",
                    color_discrete_sequence=["#0D9E75"],text="Count")
        fig3.update_traces(textposition="outside",textfont_size=11)
        fig3.update_layout(**BG,
            title=dict(text=f"RESOLUTION REASONS — THIS WEEK ({len(res_week)} TICKETS)",
                       font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
            xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
            yaxis=dict(showgrid=False,title=""))
        st.plotly_chart(fig3,use_container_width=True,config={"displayModeBar":False})
    else:
        st.markdown(f"""<div style="{CARD}text-align:center;padding:40px">
          <div style="font-size:11px;color:#888">RESOLUTION REASONS — THIS WEEK</div>
          <div style="font-size:14px;color:#aaa;margin-top:12px">No tickets resolved yet this week</div>
        </div>""", unsafe_allow_html=True)

with c4:
    if rb_mo:
        df_mo=pd.DataFrame(sorted(rb_mo.items(),key=lambda x:x[1])[-8:],columns=["Reason","Count"])
        fig4=px.bar(df_mo,x="Count",y="Reason",orientation="h",
                    color_discrete_sequence=["#7C3AED"],text="Count")
        fig4.update_traces(textposition="outside",textfont_size=11)
        fig4.update_layout(**BG,
            title=dict(text=f"RESOLUTION REASONS — THIS MONTH ({len(res_mon)} TICKETS)",
                       font=dict(size=11,color="#1a1a18"),x=0,xanchor="left",pad=dict(l=4,t=4)),
            xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
            yaxis=dict(showgrid=False,title=""))
        st.plotly_chart(fig4,use_container_width=True,config={"displayModeBar":False})

st.markdown("<hr style='border:none;border-top:1px solid #e8e6e0;margin:8px 0 14px'>",unsafe_allow_html=True)

# ── Tables ────────────────────────────────────────────────
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
            "Created":fdate(b.get("fields",{}).get("created",""))} for b in bugs]),
            use_container_width=True,hide_index=True,
            column_config={
                "Ticket":st.column_config.LinkColumn("Ticket",width="small",display_text=r"(INC-\d+)")})
    else:
        st.success("No open production bugs 🎉")

st.markdown(f"<p style='text-align:center;font-size:12px;color:#aaa;margin-top:20px;padding-top:16px;border-top:1px solid #e8e6e0'>Support Operations Live Dashboard · groundgamehealth.atlassian.net · {now_str}</p>",unsafe_allow_html=True)