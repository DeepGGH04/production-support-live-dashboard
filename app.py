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

st.set_page_config(
    page_title="Support Ops — Live Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  /* Force light background throughout */
  html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"],
  [data-testid="block-container"] {
      background-color: #F4F3EF !important;
      color: #1a1a18 !important;
  }
  [data-testid="stBlock"], [data-testid="stVerticalBlock"],
  [data-testid="stHorizontalBlock"] {
      background-color: transparent !important;
  }
  /* Hide streamlit chrome */
  #MainMenu, footer, header { visibility: hidden; }
  [data-testid="stToolbar"] { display: none; }
  .block-container { padding-top: 1.5rem !important; max-width: 1200px; }

  /* Header */
  .dash-header {
      background: #0F1F3D; color: white; border-radius: 14px;
      padding: 22px 32px; margin-bottom: 20px;
      display: flex; justify-content: space-between; align-items: center;
  }
  .dash-title { font-size: 20px; font-weight: 600; margin: 0; color: white; }
  .dash-sub   { font-size: 12px; color: #94A3B8; margin: 3px 0 0; }
  .live-pill  {
      background: #0D9E75; color: white; border-radius: 20px;
      padding: 5px 14px; font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: .05em; white-space: nowrap;
  }

  /* KPI cards */
  .kpi {
      background: white; border-radius: 12px; padding: 18px 20px;
      border: 1px solid #e8e6e0; height: 110px;
  }
  .kpi-lbl { font-size: 11px; color: #888; margin-bottom: 6px; }
  .kpi-val { font-size: 34px; font-weight: 700; color: #1a1a18; line-height: 1.1; }
  .kpi-sub { font-size: 11px; color: #888; margin-top: 4px; }
  .up   { color: #C0392B; font-weight: 600; }
  .down { color: #27700F; font-weight: 600; }

  /* Insight cards */
  .ins {
      border-radius: 0 10px 10px 0; padding: 14px 16px;
      border-top: 1px solid #e8e6e0; border-right: 1px solid #e8e6e0;
      border-bottom: 1px solid #e8e6e0; background: white; height: 100px;
  }
  .ins-d { border-left: 4px solid #EF4444; }
  .ins-w { border-left: 4px solid #F59E0B; }
  .ins-i { border-left: 4px solid #3B82F6; }
  .ins-ttl { font-weight: 700; font-size: 12px; margin-bottom: 5px; }
  .ins-ttl-d { color: #991B1B; }
  .ins-ttl-w { color: #92400E; }
  .ins-ttl-i { color: #1E40AF; }
  .ins-body { font-size: 11px; color: #555; line-height: 1.5; }

  /* Section label */
  .sec-lbl {
      font-size: 10px; font-weight: 700; letter-spacing: .1em;
      text-transform: uppercase; color: #888; margin: 16px 0 8px;
  }

  /* Panel wrapper */
  .panel {
      background: white; border-radius: 12px;
      border: 1px solid #e8e6e0; padding: 16px 18px;
  }

  /* Refresh button */
  div[data-testid="stButton"] > button {
      background: #0F1F3D !important; color: white !important;
      border-radius: 8px !important; border: none !important;
      padding: 8px 20px !important; font-weight: 500 !important;
      width: 100%;
  }
  div[data-testid="stButton"] > button:hover {
      background: #1a3560 !important;
  }

  /* Dataframe */
  [data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
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

def sow():
    t = datetime.now(timezone.utc)
    return (t - timedelta(days=t.weekday())).strftime("%Y-%m-%d 00:00")
def som():
    return datetime.now(timezone.utc).strftime("%Y-%m-01 00:00")
def som20():
    t = datetime.now(timezone.utc)
    return (t.replace(day=1) + timedelta(days=20)).strftime("%Y-%m-%d 00:00")

def q_active():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY {NOISE}'
def q_monday():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution=EMPTY AND createdDate<="{sow()}" {NOISE}'
def q_res_week():
    return f'project={PROJECT} AND resolved>="{som20()}" AND "Request Type" NOT IN ({EXCL}) AND issue>INC-9800 {NOISE}'
def q_res_month():
    return f'project={PROJECT} AND "Request Type" NOT IN ({EXCL}) AND resolution!=EMPTY AND resolved>="{som()}" AND issue>INC-9800 {NOISE}'

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

def sname(i):
    raw = i.get("fields", {}).get("status", {}).get("name", "?")
    return STATUS_MAP.get(raw, raw)
def age(i):
    c = i.get("fields", {}).get("created", "")
    return (datetime.now(timezone.utc) - datetime.fromisoformat(c.replace("Z", "+00:00"))).days if c else 0
def fdate(iso):
    try: return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b") if iso else ""
    except: return ""
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

# Chart helper — consistent styling
CHART_LAYOUT = dict(
    paper_bgcolor="white", plot_bgcolor="white",
    margin=dict(t=10, b=10, l=10, r=10), height=260,
    font=dict(family="sans-serif", size=11, color="#475569"),
)

# ── Header ────────────────────────────────────────────────
now_str = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
h1, h2 = st.columns([5, 1])
with h1:
    st.markdown(f"""
    <div class="dash-header">
      <div>
        <p class="dash-title">Production Support Jira Board — Live Dashboard</p>
        <p class="dash-sub">Last updated: {now_str}</p>
      </div>
      <span class="live-pill">● Live · groundgamehealth</span>
    </div>""", unsafe_allow_html=True)
with h2:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Data", use_container_width=True):
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
net_cls  = "up" if net > 0 else "down"
aged     = sorted(active, key=lambda i: -age(i))
oldest   = aged[0] if aged else None

# ── KPI row ───────────────────────────────────────────────
st.markdown('<p class="sec-lbl">Key metrics at a glance</p>', unsafe_allow_html=True)
k1, k2, k3, k4 = st.columns(4)
cards = [
    (k1, "Active tickets",      str(len(active)),    f'<span class="{net_cls}">{net_sign}{net}</span> vs Monday ({len(monday)})'),
    (k2, "Resolved this week",  str(len(res_week)),  "tickets closed this week"),
    (k3, "Resolved this month", str(len(res_mon)),   "across all request types"),
    (k4, "Oldest open ticket",  f'{age(oldest) if oldest else 0}d',
         f'<span style="color:#C0392B;font-weight:600">{oldest["key"] if oldest else "N/A"}</span>'),
]
for col, lbl, val, sub in cards:
    with col:
        st.markdown(f"""<div class="kpi">
          <div class="kpi-lbl">{lbl}</div>
          <div class="kpi-val">{val}</div>
          <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── Insights ──────────────────────────────────────────────
st.markdown('<p class="sec-lbl">Key insights</p>', unsafe_allow_html=True)
i1, i2, i3 = st.columns(3)
trend = "Triage session recommended." if net > 5 else "Backlog is stable."
oldest_age = age(oldest) if oldest else 0
oldest_key = oldest["key"] if oldest else "N/A"
bug_msg = f"{len(bugs)} active production bug{'s' if len(bugs)!=1 else ''} in the backlog. Requires sprint commitment." if bugs else "No open production bugs 🎉"

for col, cls, tcls, title, body in [
    (i1, "ins-d", "ins-ttl-d", "Backlog trend",    f"Net {net_sign}{net} tickets this week — active count is {len(active)}. {trend}"),
    (i2, "ins-w", "ins-ttl-w", "Aging tickets",    f"Oldest open ticket is {oldest_age} days old ({oldest_key}). Review tickets aged over 60 days."),
    (i3, "ins-i", "ins-ttl-i", "Production bugs",  bug_msg),
]:
    with col:
        st.markdown(f"""<div class="ins {cls}">
          <div class="ins-ttl {tcls}">{title}</div>
          <div class="ins-body">{body}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── Charts row 1 ──────────────────────────────────────────
c1, c2 = st.columns(2)

with c1:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<p class="sec-lbl">Active ticket status</p>', unsafe_allow_html=True)
    sc = {}
    for i in active:
        s = sname(i); sc[s] = sc.get(s, 0) + 1
    if sc:
        fig = go.Figure(go.Pie(
            labels=list(sc.keys()), values=list(sc.values()),
            hole=0.6, textposition="inside",
            marker_colors=["#F59E0B","#9CA3AF","#3B82F6","#EF4444","#0D9E75","#8B5CF6","#14B8A6"],
        ))
        fig.update_layout(**CHART_LAYOUT,
            legend=dict(orientation="h", yanchor="top", y=-0.05, font=dict(size=10)))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with c2:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<p class="sec-lbl">Active by request type</p>', unsafe_allow_html=True)
    rc = {}
    for i in active:
        v = get_rt(i)
        if v: rc[v] = rc.get(v, 0) + 1
    if rc:
        df_rt = pd.DataFrame(sorted(rc.items(), key=lambda x: x[1]), columns=["Type", "Count"])
        fig2 = px.bar(df_rt, x="Count", y="Type", orientation="h",
                      color_discrete_sequence=["#3B82F6"],
                      text="Count")
        fig2.update_traces(textposition="outside", textfont_size=10)
        fig2.update_layout(**CHART_LAYOUT,
            xaxis=dict(showgrid=True, gridcolor="#F0EEEA", title=""),
            yaxis=dict(showgrid=False, title=""))
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

# ── Charts row 2 ──────────────────────────────────────────
c3, c4 = st.columns(2)

with c3:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(f'<p class="sec-lbl">Resolution reasons — this week ({len(res_week)} tickets)</p>', unsafe_allow_html=True)
    rb_wk = resb(res_week)
    if rb_wk:
        df_wk = pd.DataFrame(sorted(rb_wk.items(), key=lambda x: x[1])[-7:], columns=["Reason","Count"])
        fig3 = px.bar(df_wk, x="Count", y="Reason", orientation="h",
                      color_discrete_sequence=["#0D9E75"], text="Count")
        fig3.update_traces(textposition="outside", textfont_size=10)
        fig3.update_layout(**CHART_LAYOUT,
            xaxis=dict(showgrid=True, gridcolor="#F0EEEA", title=""),
            yaxis=dict(showgrid=False, title=""))
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with c4:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown(f'<p class="sec-lbl">Resolution reasons — this month ({len(res_mon)} tickets)</p>', unsafe_allow_html=True)
    rb_mo = resb(res_mon)
    if rb_mo:
        df_mo = pd.DataFrame(sorted(rb_mo.items(), key=lambda x: x[1])[-8:], columns=["Reason","Count"])
        fig4 = px.bar(df_mo, x="Count", y="Reason", orientation="h",
                      color_discrete_sequence=["#7C3AED"], text="Count")
        fig4.update_traces(textposition="outside", textfont_size=10)
        fig4.update_layout(**CHART_LAYOUT,
            xaxis=dict(showgrid=True, gridcolor="#F0EEEA", title=""),
            yaxis=dict(showgrid=False, title=""))
        st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")

# ── Tables ────────────────────────────────────────────────
t1, t2 = st.columns(2)

with t1:
    st.markdown('<p class="sec-lbl">Aging backlog — oldest open tickets</p>', unsafe_allow_html=True)
    if aged:
        df_age = pd.DataFrame([{
            "Ticket":     i["key"],
            "Summary":    i.get("fields",{}).get("summary","")[:50],
            "Age (days)": age(i),
            "Status":     sname(i),
        } for i in aged[:7]])
        st.dataframe(df_age, use_container_width=True, hide_index=True,
            column_config={
                "Ticket":     st.column_config.TextColumn(width="small"),
                "Age (days)": st.column_config.NumberColumn(format="%dd"),
            })

with t2:
    st.markdown(f'<p class="sec-lbl">Open production bugs ({len(bugs)})</p>', unsafe_allow_html=True)
    if bugs:
        df_bugs = pd.DataFrame([{
            "Ticket":  b["key"],
            "Summary": b.get("fields",{}).get("summary","")[:48],
            "Created": fdate(b.get("fields",{}).get("created","")),
        } for b in bugs])
        st.dataframe(df_bugs, use_container_width=True, hide_index=True,
            column_config={"Ticket": st.column_config.TextColumn(width="small")})
    else:
        st.success("No open production bugs 🎉")

st.markdown(f"""
<p style="text-align:center;font-size:11px;color:#aaa;margin-top:24px;
padding-top:16px;border-top:1px solid #e8e6e0">
Support Operations Live Dashboard · groundgamehealth.atlassian.net · {now_str}
</p>""", unsafe_allow_html=True)