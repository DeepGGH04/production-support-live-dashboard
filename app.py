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
  /* Form = header */
  div[data-testid="stForm"]{
      background:#0F1F3D!important;border-radius:12px!important;
      border:none!important;padding:20px 28px!important;margin-bottom:16px!important;
  }
  div[data-testid="stForm"] > div > div {background:transparent!important}
  div[data-testid="stForm"] button{
      background:rgba(255,255,255,.15)!important;color:white!important;
      border:1px solid rgba(255,255,255,.35)!important;border-radius:8px!important;
      font-size:14px!important;font-weight:600!important;padding:10px 0!important;
      width:100%!important;margin-top:4px!important;
  }
  div[data-testid="stForm"] button:hover{background:rgba(255,255,255,.28)!important}
  div[data-testid="stForm"] p{color:white!important}
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

def sow():
    t=datetime.now(timezone.utc); return (t-timedelta(days=t.weekday())).strftime("%Y-%m-%d 00:00")
def som():  return datetime.now(timezone.utc).strftime("%Y-%m-01 00:00")
def som20():
    t=datetime.now(timezone.utc); return (t.replace(day=1)+timedelta(days=20)).strftime("%Y-%m-%d 00:00")

def q_active():    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY {NOISE}'
def q_monday():    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY AND createdDate<="{sow()}" {NOISE}'
def q_res_week():  return f'project={PROJECT} AND resolved>="{som20()}" AND "Request Type" NOT IN ({EXCL}) AND issue>INC-9800 {NOISE}'
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
    return (datetime.now(timezone.utc)-datetime.fromisoformat(c.replace("Z","+00:00"))).days if c else 0
def fdate(iso):
    try: return datetime.fromisoformat(iso.replace("Z","+00:00")).strftime("%d %b") if iso else ""
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
        "bugs":(f'project={PROJECT} AND status=PROD_BUG AND resolution=EMPTY',20)}
    with ThreadPoolExecutor(max_workers=5) as ex:
        fut={k:ex.submit(jql_fetch,q,lim) for k,(q,lim) in qs.items()}
        return {k:fut[k].result() for k in fut}

now_str = datetime.now(ZoneInfo("America/New_York")).strftime("%d %b %Y, %H:%M EST")
CARD = "background:white;border-radius:12px;border:1px solid #e8e6e0;padding:20px 24px;"
LBL  = "font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#888;margin-bottom:12px;display:block"

# ── Header ────────────────────────────────────────────────
with st.form("hdr"):
    ca, cb, cc = st.columns([6, 2, 1])
    with ca:
        st.markdown(f"""
        <div style="margin:2px 0 0">
          <div style="font-size:22px;font-weight:700;color:white;margin-bottom:6px;line-height:1.2">
            Production Support Jira Board — Live Dashboard
          </div>
          <div style="font-size:13px;color:#94A3B8">Last updated: {now_str}</div>
        </div>""", unsafe_allow_html=True)
    with cb:
        st.markdown("""
        <div style="display:flex;align-items:center;height:100%;padding-top:14px">
          <div style="background:#0D9E75;color:white;border-radius:20px;
            padding:7px 20px;font-size:12px;font-weight:700;letter-spacing:.05em;white-space:nowrap">
            ● LIVE · GROUNDGAMEHEALTH
          </div>
        </div>""", unsafe_allow_html=True)
    with cc:
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        submitted = st.form_submit_button("🔄 Refresh", use_container_width=True)
    if submitted:
        st.cache_data.clear(); st.rerun()

# ── Load ──────────────────────────────────────────────────
with st.spinner("Loading live data from Jira…"):
    try: data = load_data()
    except Exception as e: st.error(f"⚠️ {e}"); st.stop()

active=data["active"]; monday=data["monday"]
res_week=data["res_week"]; res_mon=data["res_month"]; bugs=data["bugs"]
net=len(active)-len(monday); ns="+" if net>=0 else ""; nc="#C0392B" if net>0 else "#27700F"
aged=sorted(active,key=lambda i:-age(i)); oldest=aged[0] if aged else None
oa=age(oldest) if oldest else 0; ok=oldest["key"] if oldest else "N/A"

# ── KPI cards ─────────────────────────────────────────────
st.markdown(f"<span style='{LBL}'>Key metrics at a glance</span>", unsafe_allow_html=True)
for col, lbl, val, sub in zip(st.columns(4), [
    "Active tickets","Resolved this week","Resolved this month","Oldest open ticket"
],[
    str(len(active)), str(len(res_week)), str(len(res_mon)), f"{oa}d"
],[
    f'<span style="color:{nc};font-weight:600;font-size:13px">{ns}{net}</span> <span style="font-size:13px;color:#888">vs Monday ({len(monday)})</span>',
    '<span style="font-size:13px;color:#888">tickets closed this week</span>',
    '<span style="font-size:13px;color:#888">across all request types</span>',
    f'<span style="color:#C0392B;font-weight:600;font-size:13px">{ok}</span>',
]):
    with col:
        st.markdown(f"""
        <div style="{CARD}">
          <div style="font-size:13px;color:#888;margin-bottom:10px">{lbl}</div>
          <div style="font-size:40px;font-weight:700;color:#1a1a18;line-height:1;margin-bottom:8px">{val}</div>
          <div>{sub}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ── Insight cards ─────────────────────────────────────────
st.markdown(f"<span style='{LBL}'>Key insights</span>", unsafe_allow_html=True)
trend = "Triage session recommended." if net>5 else "Backlog is stable."
bmsg  = f"{len(bugs)} active production bug{'s' if len(bugs)!=1 else ''} in the backlog. Requires sprint commitment." if bugs else "No open production bugs 🎉"
for col, (bc,tc,title,body) in zip(st.columns(3), [
    ("#EF4444","#991B1B","Backlog trend",  f"Net {ns}{net} tickets this week — active count is {len(active)}. {trend}"),
    ("#F59E0B","#92400E","Aging tickets",  f"Oldest open ticket is {oa} days old ({ok}). Review tickets aged over 60 days."),
    ("#3B82F6","#1E40AF","Production bugs", bmsg),
]):
    with col:
        st.markdown(f"""
        <div style="background:white;border-left:4px solid {bc};
          border-top:1px solid #e8e6e0;border-right:1px solid #e8e6e0;border-bottom:1px solid #e8e6e0;
          border-radius:0 10px 10px 0;padding:16px 18px;min-height:90px">
          <div style="font-size:14px;font-weight:700;color:{tc};margin-bottom:6px">{title}</div>
          <div style="font-size:13px;color:#555;line-height:1.6">{body}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ── Charts row 1 ──────────────────────────────────────────
BG = dict(paper_bgcolor="white", plot_bgcolor="white",
          margin=dict(t=10,b=10,l=10,r=24), height=320,
          font=dict(family="sans-serif", size=12, color="#475569"))

sc={}
for i in active: s=sname(i); sc[s]=sc.get(s,0)+1
rc={}
for i in active:
    v=get_rt(i)
    if v: rc[v]=rc.get(v,0)+1

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"""
    <div style="{CARD}padding:18px 20px;">
      <span style="{LBL}">Active ticket status</span>
    </div>""", unsafe_allow_html=True)
    fig=go.Figure(go.Pie(labels=list(sc.keys()),values=list(sc.values()),
        hole=0.58,textposition="inside",textinfo="percent",
        marker_colors=["#F59E0B","#9CA3AF","#3B82F6","#EF4444","#0D9E75","#8B5CF6","#14B8A6"]))
    fig.update_layout(**BG,legend=dict(orientation="h",xanchor="center",x=0.5,
                                       yanchor="top",y=-0.04,font=dict(size=11)))
    st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False})

with c2:
    st.markdown(f"""
    <div style="{CARD}padding:18px 20px;">
      <span style="{LBL}">Active by request type</span>
    </div>""", unsafe_allow_html=True)
    df_rt=pd.DataFrame(sorted(rc.items(),key=lambda x:x[1]),columns=["Type","Count"])
    fig2=px.bar(df_rt,x="Count",y="Type",orientation="h",
                color_discrete_sequence=["#3B82F6"],text="Count")
    fig2.update_traces(textposition="outside",textfont_size=11)
    fig2.update_layout(**BG,xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
                       yaxis=dict(showgrid=False,title="",automargin=True))
    st.plotly_chart(fig2,use_container_width=True,config={"displayModeBar":False})

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ── Charts row 2 ──────────────────────────────────────────
rb_wk=resb(res_week); rb_mo=resb(res_mon)
c3, c4 = st.columns(2)

with c3:
    st.markdown(f"""
    <div style="{CARD}padding:18px 20px;">
      <span style="{LBL}">Resolution reasons — this week ({len(res_week)} tickets)</span>
    </div>""", unsafe_allow_html=True)
    if rb_wk:
        df_wk=pd.DataFrame(sorted(rb_wk.items(),key=lambda x:x[1])[-7:],columns=["Reason","Count"])
        fig3=px.bar(df_wk,x="Count",y="Reason",orientation="h",
                    color_discrete_sequence=["#0D9E75"],text="Count")
        fig3.update_traces(textposition="outside",textfont_size=11)
        fig3.update_layout(**BG,xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
                           yaxis=dict(showgrid=False,title=""))
        st.plotly_chart(fig3,use_container_width=True,config={"displayModeBar":False})

with c4:
    st.markdown(f"""
    <div style="{CARD}padding:18px 20px;">
      <span style="{LBL}">Resolution reasons — this month ({len(res_mon)} tickets)</span>
    </div>""", unsafe_allow_html=True)
    if rb_mo:
        df_mo=pd.DataFrame(sorted(rb_mo.items(),key=lambda x:x[1])[-8:],columns=["Reason","Count"])
        fig4=px.bar(df_mo,x="Count",y="Reason",orientation="h",
                    color_discrete_sequence=["#7C3AED"],text="Count")
        fig4.update_traces(textposition="outside",textfont_size=11)
        fig4.update_layout(**BG,xaxis=dict(showgrid=True,gridcolor="#F0EEEA",title=""),
                           yaxis=dict(showgrid=False,title=""))
        st.plotly_chart(fig4,use_container_width=True,config={"displayModeBar":False})

st.markdown("<hr style='border:none;border-top:1px solid #e8e6e0;margin:8px 0 14px'>",unsafe_allow_html=True)

# ── Tables ────────────────────────────────────────────────
t1, t2 = st.columns(2)
with t1:
    st.markdown(f"<span style='{LBL}'>Aging backlog — oldest open tickets</span>", unsafe_allow_html=True)
    if aged:
        st.dataframe(pd.DataFrame([{
            "Ticket":i["key"],"Summary":i.get("fields",{}).get("summary","")[:50],
            "Age (d)":age(i),"Status":sname(i)} for i in aged[:7]]),
            use_container_width=True,hide_index=True,
            column_config={"Ticket":st.column_config.TextColumn(width="small"),
                           "Age (d)":st.column_config.NumberColumn(width="small")})

with t2:
    st.markdown(f"<span style='{LBL}'>Open production bugs ({len(bugs)})</span>", unsafe_allow_html=True)
    if bugs:
        st.dataframe(pd.DataFrame([{
            "Ticket":b["key"],"Summary":b.get("fields",{}).get("summary","")[:48],
            "Created":fdate(b.get("fields",{}).get("created",""))} for b in bugs]),
            use_container_width=True,hide_index=True,
            column_config={"Ticket":st.column_config.TextColumn(width="small")})
    else:
        st.success("No open production bugs 🎉")

st.markdown(f"""<p style="text-align:center;font-size:12px;color:#aaa;margin-top:20px;
  padding-top:16px;border-top:1px solid #e8e6e0">
  Support Operations Live Dashboard · groundgamehealth.atlassian.net · {now_str}
</p>""", unsafe_allow_html=True)