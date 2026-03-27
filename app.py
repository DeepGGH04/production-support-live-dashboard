"""
Support Ops — Live Jira Dashboard (Streamlit)
Deploy: https://streamlit.io/cloud
"""
import os
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# ── Page config ───────────────────────────────────────────
st.set_page_config(
    page_title="Support Ops — Live Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS to match existing design ──────────────────
st.markdown("""
<style>
    .main { background-color: #F4F3EF; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1200px; }
    
    .header-box {
        background: #0F1F3D; color: white; border-radius: 14px;
        padding: 24px 32px; margin-bottom: 24px;
        display: flex; justify-content: space-between; align-items: center;
    }
    .header-title { font-size: 22px; font-weight: 600; margin: 0; }
    .header-sub { font-size: 12px; color: #94A3B8; margin: 4px 0 0; }
    .status-pill {
        background: #0D9E75; color: white; border-radius: 20px;
        padding: 6px 16px; font-size: 12px; font-weight: 700;
        text-transform: uppercase; letter-spacing: .05em;
    }
    .kpi-card {
        background: white; border-radius: 12px; padding: 20px 22px;
        border: 1px solid #e8e6e0; height: 100%;
    }
    .kpi-label { font-size: 12px; color: #888; margin-bottom: 8px; }
    .kpi-value { font-size: 36px; font-weight: 700; color: #1a1a18; line-height: 1; margin-bottom: 6px; }
    .kpi-sub   { font-size: 12px; color: #888; }
    .kpi-up    { color: #C0392B; font-weight: 600; }
    .kpi-down  { color: #27700F; font-weight: 600; }

    .insight-danger { border-left: 4px solid #EF4444; background: white; border-radius: 0 10px 10px 0;
        padding: 14px 16px; border-top:1px solid #e8e6e0; border-right:1px solid #e8e6e0; border-bottom:1px solid #e8e6e0; }
    .insight-warn   { border-left: 4px solid #F59E0B; background: white; border-radius: 0 10px 10px 0;
        padding: 14px 16px; border-top:1px solid #e8e6e0; border-right:1px solid #e8e6e0; border-bottom:1px solid #e8e6e0; }
    .insight-info   { border-left: 4px solid #3B82F6; background: white; border-radius: 0 10px 10px 0;
        padding: 14px 16px; border-top:1px solid #e8e6e0; border-right:1px solid #e8e6e0; border-bottom:1px solid #e8e6e0; }
    .insight-title-danger { color: #991B1B; font-weight: 700; font-size: 13px; margin-bottom: 4px; }
    .insight-title-warn   { color: #92400E; font-weight: 700; font-size: 13px; margin-bottom: 4px; }
    .insight-title-info   { color: #1E40AF; font-weight: 700; font-size: 13px; margin-bottom: 4px; }
    .insight-body { font-size: 12px; color: #555; line-height: 1.5; }

    .section-label {
        font-size: 10px; font-weight: 700; letter-spacing: .1em;
        text-transform: uppercase; color: #888; margin-bottom: 8px;
    }
    .panel {
        background: white; border-radius: 12px; padding: 20px 22px;
        border: 1px solid #e8e6e0;
    }
    div[data-testid="stMetric"] { background: white; border-radius: 12px; padding: 16px; border: 1px solid #e8e6e0; }
    .stButton button { border-radius: 8px; border: 1px solid rgba(255,255,255,0.25);
        background: transparent; color: white; }
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ── Credentials ───────────────────────────────────────────
try:
    JIRA_BASE  = st.secrets["JIRA_BASE_URL"].rstrip("/")
    JIRA_EMAIL = st.secrets["JIRA_EMAIL"]
    JIRA_TOKEN = st.secrets["JIRA_API_TOKEN"]
except Exception:
    JIRA_BASE  = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
    JIRA_TOKEN = os.getenv("JIRA_API_TOKEN", "")

PROJECT = '"GGH Production"'
AUTH    = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
HEADERS = {"Accept": "application/json"}

EXCL = (
    'EMPTY,"Absorb Support (INC)","New Implify/dialer Enhancements (INC)",'
    '"Enhancements (INC)","File Ingestion (INC)","SOC incident (INC)",'
    '"Adhoc File Pickup (INC)","8X8 Access (INC)","Access Modification (INC)",'
    '"Request access (INC)","Revoke access (INC)","Onboard New CBO (INC)"'
)
NOISE = ('AND summary !~ "Daily checkout" AND summary !~ "IMPLIFY Training" '
         'AND summary !~ "Grafana"')
STATUS_MAP = {
    "Work InProgress":  "Work In Progress",
    "Work in progress": "Work In Progress",
    "TODO":             "To Do",
}


# ── Date helpers ──────────────────────────────────────────
def sow():
    t = datetime.now(timezone.utc)
    return (t - timedelta(days=t.weekday())).strftime("%Y-%m-%d 00:00")

def som():
    return datetime.now(timezone.utc).strftime("%Y-%m-01 00:00")

def som20():
    t = datetime.now(timezone.utc)
    return (t.replace(day=1) + timedelta(days=20)).strftime("%Y-%m-%d 00:00")


# ── JQL queries ───────────────────────────────────────────
def q_active():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY {NOISE}'

def q_monday():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY AND createdDate<="{sow()}" {NOISE}'

def q_res_week():
    return f'project={PROJECT} AND resolved>="{som20()}" AND "Request Type" NOT IN ({EXCL}) AND issue>INC-9800 {NOISE}'

def q_res_month():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution!=EMPTY AND resolved>="{som()}" AND issue>INC-9800 {NOISE}'


# ── Fetch ─────────────────────────────────────────────────
def jql_fetch(jql: str, limit: int = 500) -> list:
    url   = f"{JIRA_BASE}/rest/api/3/search/jql"
    flds  = "summary,status,created,updated,issuetype,priority,resolutiondate,resolution,customfield_10010"
    issues, token = [], None
    while len(issues) < limit:
        params = {"jql": jql, "fields": flds, "maxResults": min(100, limit - len(issues))}
        if token:
            params["nextPageToken"] = token
        r = requests.get(url, auth=AUTH, headers=HEADERS, params=params)
        r.raise_for_status()
        data  = r.json()
        batch = data.get("issues", [])
        issues += batch
        token  = data.get("nextPageToken")
        if not batch or not token:
            break
    return issues


# ── Helpers ───────────────────────────────────────────────
def sname(i):
    raw = i.get("fields", {}).get("status", {}).get("name", "?")
    return STATUS_MAP.get(raw, raw)

def age(i):
    c = i.get("fields", {}).get("created", "")
    return (datetime.now(timezone.utc) - datetime.fromisoformat(c.replace("Z", "+00:00"))).days if c else 0

def fdate(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b") if iso else ""
    except Exception:
        return ""

def get_rt(i):
    f = i.get("fields", {}).get("customfield_10010") or {}
    n = f.get("requestType", {}).get("name", "").strip() if isinstance(f, dict) else ""
    return n if n and n.lower() not in ("none", "other", "") else None

def resb(issues):
    c = {}
    for i in issues:
        r = (i.get("fields", {}).get("resolution") or {}).get("name", "") \
            or i.get("fields", {}).get("status", {}).get("name", "Other")
        c[r] = c.get(r, 0) + 1
    return c


# ── Load all data ─────────────────────────────────────────
@st.cache_data(ttl=0, show_spinner=False)
def load_data():
    qs = {
        "active":    (q_active(),    500),
        "monday":    (q_monday(),    500),
        "res_week":  (q_res_week(),  500),
        "res_month": (q_res_month(), 500),
        "bugs":      (f'project={PROJECT} AND status=PROD_BUG AND resolution=EMPTY', 20),
    }
    with ThreadPoolExecutor(max_workers=5) as ex:
        fut = {k: ex.submit(jql_fetch, q, lim) for k, (q, lim) in qs.items()}
        return {k: fut[k].result() for k in fut}


# ══════════════════════════════════════════════════════════
# RENDER
# ══════════════════════════════════════════════════════════

# ── Header ────────────────────────────────────────────────
now_str = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown(f"""
    <div class="header-box">
        <div>
            <p class="header-title">Production Support Jira Board — Live Dashboard</p>
            <p class="header-sub">Last updated: {now_str}</p>
        </div>
        <div>
            <span class="status-pill">● Live · groundgamehealth</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ── Refresh button ────────────────────────────────────────
with col_h2:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄  Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Load ──────────────────────────────────────────────────
with st.spinner("Fetching live data from Jira…"):
    try:
        data = load_data()
    except Exception as e:
        st.error(f"⚠️ Could not load data: {e}")
        st.stop()

active   = data["active"]
monday   = data["monday"]
res_week = data["res_week"]
res_mon  = data["res_month"]
bugs     = data["bugs"]

net      = len(active) - len(monday)
net_sign = "+" if net >= 0 else ""
net_col  = "kpi-up" if net > 0 else "kpi-down"

aged     = sorted(active, key=lambda i: -age(i))
oldest   = aged[0] if aged else None
oldest_age = age(oldest) if oldest else 0
oldest_key = oldest["key"] if oldest else "N/A"

# ── KPI Cards ─────────────────────────────────────────────
st.markdown('<p class="section-label">Key metrics at a glance</p>', unsafe_allow_html=True)
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Active tickets</div>
    <div class="kpi-value">{len(active)}</div>
    <div class="kpi-sub"><span class="{net_col}">{net_sign}{net}</span> vs Monday ({len(monday)})</div>
    </div>""", unsafe_allow_html=True)
with k2:
    st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Resolved this week</div>
    <div class="kpi-value">{len(res_week)}</div>
    <div class="kpi-sub">tickets closed this week</div>
    </div>""", unsafe_allow_html=True)
with k3:
    st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Resolved this month</div>
    <div class="kpi-value">{len(res_mon)}</div>
    <div class="kpi-sub">across all request types</div>
    </div>""", unsafe_allow_html=True)
with k4:
    st.markdown(f"""<div class="kpi-card"><div class="kpi-label">Oldest open ticket</div>
    <div class="kpi-value">{oldest_age}d</div>
    <div class="kpi-sub" style="color:#C0392B;font-weight:600">{oldest_key}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Insights ──────────────────────────────────────────────
st.markdown('<p class="section-label">Key insights</p>', unsafe_allow_html=True)
i1, i2, i3 = st.columns(3)
with i1:
    trend = "Triage session recommended." if net > 5 else "Backlog is stable."
    st.markdown(f"""<div class="insight-danger">
    <div class="insight-title-danger">Backlog trend</div>
    <div class="insight-body">Net {net_sign}{net} tickets this week — active count is {len(active)}. {trend}</div>
    </div>""", unsafe_allow_html=True)
with i2:
    st.markdown(f"""<div class="insight-warn">
    <div class="insight-title-warn">Aging tickets</div>
    <div class="insight-body">Oldest open ticket is {oldest_age} days old ({oldest_key}). Review tickets aged over 60 days.</div>
    </div>""", unsafe_allow_html=True)
with i3:
    bug_msg = f"{len(bugs)} active production bug{'s' if len(bugs)!=1 else ''} in the backlog. Requires sprint commitment." if bugs else "No open production bugs 🎉"
    st.markdown(f"""<div class="insight-info">
    <div class="insight-title-info">Production bugs</div>
    <div class="insight-body">{bug_msg}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Charts row ────────────────────────────────────────────
c1, c2 = st.columns(2)

with c1:
    st.markdown('<p class="section-label">Active ticket status</p>', unsafe_allow_html=True)
    sc = {}
    for i in active:
        s = sname(i); sc[s] = sc.get(s, 0) + 1
    if sc:
        fig = px.pie(values=list(sc.values()), names=list(sc.keys()), hole=0.6,
                     color_discrete_sequence=["#F59E0B","#9CA3AF","#3B82F6","#EF4444","#0D9E75","#8B5CF6","#EC4899","#14B8A6"])
        fig.update_layout(margin=dict(t=0,b=0,l=0,r=0), height=260,
                          paper_bgcolor="white", plot_bgcolor="white",
                          legend=dict(orientation="h", yanchor="bottom", y=-0.3))
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

with c2:
    st.markdown('<p class="section-label">Active by request type</p>', unsafe_allow_html=True)
    rc = {}
    for i in active:
        v = get_rt(i)
        if v: rc[v] = rc.get(v, 0) + 1
    if rc:
        df_rt = pd.DataFrame(sorted(rc.items(), key=lambda x: x[1]), columns=["Type", "Count"])
        fig2 = px.bar(df_rt, x="Count", y="Type", orientation="h",
                      color_discrete_sequence=["#3B82F6"])
        fig2.update_layout(margin=dict(t=0,b=0,l=0,r=0), height=260,
                           paper_bgcolor="white", plot_bgcolor="white",
                           xaxis=dict(showgrid=True, gridcolor="#F0EEEA"),
                           yaxis=dict(showgrid=False))
        st.plotly_chart(fig2, use_container_width=True)

# ── Resolution charts ─────────────────────────────────────
c3, c4 = st.columns(2)
with c3:
    st.markdown(f'<p class="section-label">Resolution reasons — this week ({len(res_week)} tickets)</p>', unsafe_allow_html=True)
    rb_wk = resb(res_week)
    if rb_wk:
        df_wk = pd.DataFrame(sorted(rb_wk.items(), key=lambda x: x[1])[-7:], columns=["Reason","Count"])
        fig3 = px.bar(df_wk, x="Count", y="Reason", orientation="h", color_discrete_sequence=["#0D9E75"])
        fig3.update_layout(margin=dict(t=0,b=0,l=0,r=0), height=260,
                           paper_bgcolor="white", plot_bgcolor="white",
                           xaxis=dict(showgrid=True, gridcolor="#F0EEEA"),
                           yaxis=dict(showgrid=False))
        st.plotly_chart(fig3, use_container_width=True)

with c4:
    st.markdown(f'<p class="section-label">Resolution reasons — this month ({len(res_mon)} tickets)</p>', unsafe_allow_html=True)
    rb_mo = resb(res_mon)
    if rb_mo:
        df_mo = pd.DataFrame(sorted(rb_mo.items(), key=lambda x: x[1])[-8:], columns=["Reason","Count"])
        fig4 = px.bar(df_mo, x="Count", y="Reason", orientation="h", color_discrete_sequence=["#7C3AED"])
        fig4.update_layout(margin=dict(t=0,b=0,l=0,r=0), height=260,
                           paper_bgcolor="white", plot_bgcolor="white",
                           xaxis=dict(showgrid=True, gridcolor="#F0EEEA"),
                           yaxis=dict(showgrid=False))
        st.plotly_chart(fig4, use_container_width=True)

st.markdown("---")

# ── Tables row ────────────────────────────────────────────
t1, t2 = st.columns(2)

with t1:
    st.markdown('<p class="section-label">Aging backlog — oldest open tickets</p>', unsafe_allow_html=True)
    aging_data = [{"Ticket": i["key"],
                   "Summary": i.get("fields",{}).get("summary","")[:52],
                   "Age (days)": age(i),
                   "Status": sname(i)} for i in aged[:7]]
    if aging_data:
        df_age = pd.DataFrame(aging_data)
        st.dataframe(df_age, use_container_width=True, hide_index=True,
                     column_config={
                         "Age (days)": st.column_config.NumberColumn(format="%d d"),
                         "Ticket": st.column_config.TextColumn(width="small"),
                     })

with t2:
    st.markdown(f'<p class="section-label">Open production bugs ({len(bugs)})</p>', unsafe_allow_html=True)
    if bugs:
        bug_data = [{"Ticket": b["key"],
                     "Summary": b.get("fields",{}).get("summary","")[:48],
                     "Created": fdate(b.get("fields",{}).get("created",""))}
                    for b in bugs]
        st.dataframe(pd.DataFrame(bug_data), use_container_width=True, hide_index=True,
                     column_config={"Ticket": st.column_config.TextColumn(width="small")})
    else:
        st.info("No open production bugs 🎉")

st.markdown(f"""
<div style="text-align:center;font-size:11px;color:#aaa;margin-top:24px;padding-top:16px;border-top:1px solid #e8e6e0">
    Support Operations Live Dashboard · groundgamehealth.atlassian.net · {now_str}
</div>
""", unsafe_allow_html=True)
