"""
Revenue Cycle Dashboard — Streamlit edition.
Branded header, color-coded KPI tiles, and drill-down from KPI → raw rows.
"""
from datetime import datetime
from io import StringIO
import csv

import pandas as pd
import streamlit as st

import data_loader
import data_processor
import metrics as metrics_mod
import charts


st.set_page_config(
    page_title="GGH Revenue Cycle Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# Custom styling — GroundGame.Health brand (dark header, #4D65FF accent)
# -----------------------------------------------------------------------------
GGH_LOGO_URL   = "https://cdn.prod.website-files.com/67203b5d63c900c3e572178d/6759ea2a8cbdec9badfe660d_ggh-web-logo-large.png"
GGH_DARK       = "#0E3B3B"  # deep teal — matches "About Us" panel
GGH_TEAL       = "#1F7A79"  # mid teal — matches "Careers" panel, primary accent
GGH_TEAL_HOVER = "#176060"
GGH_MUTED      = "#A8C4C3"  # soft teal-gray for subtitle text

st.markdown(f"""
<style>
/* Pull the whole page up — Streamlit's default top padding is too tall */
.block-container {{
    padding-top: 1.2rem !important;
    padding-bottom: 2rem !important;
    max-width: 1600px;
}}
header[data-testid="stHeader"] {{ background: transparent; }}

/* Brand header */
.gg-header {{
    background: {GGH_DARK};
    color: #FFFFFF;
    padding: 14px 22px;
    border-radius: 12px;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 18px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}}
.gg-header .gg-logo-wrap {{
    background: #FFFFFF;
    border-radius: 8px;
    padding: 6px 10px;
    display: flex;
    align-items: center;
    height: 44px;
}}
.gg-header .gg-logo-wrap img {{ height: 28px; display: block; }}
.gg-header .gg-title {{ flex: 1; min-width: 0; }}
.gg-header h1 {{
    color: #FFFFFF;
    margin: 0;
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0.2px;
}}
.gg-header .meta {{
    color: {GGH_MUTED};
    font-size: 12px;
    margin-top: 3px;
    line-height: 1.4;
}}
.gg-header .meta b {{ color: #E6EFEF; font-weight: 600; }}
.gg-header .gg-accent {{
    width: 4px;
    align-self: stretch;
    background: {GGH_TEAL};
    border-radius: 2px;
}}

/* Primary buttons — GGH teal pill */
.stButton > button[kind="primary"] {{
    background-color: {GGH_TEAL} !important;
    border-color: {GGH_TEAL} !important;
    border-radius: 999px !important;
    font-weight: 600 !important;
    padding: 8px 18px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    transition: all 0.15s ease-in-out;
}}
.stButton > button[kind="primary"]:hover {{
    background-color: {GGH_TEAL_HOVER} !important;
    border-color: {GGH_TEAL_HOVER} !important;
    transform: translateY(-1px);
    box-shadow: 0 2px 6px rgba(0,0,0,0.12);
}}
.stButton > button[kind="primary"]:focus {{
    box-shadow: 0 0 0 3px rgba(31,122,121,0.25) !important;
}}
/* Secondary buttons (drill-down "View details" etc.) — subtle teal outline */
.stButton > button[kind="secondary"] {{
    border-radius: 999px !important;
    border-color: {GGH_TEAL} !important;
    color: {GGH_TEAL} !important;
    font-weight: 500 !important;
}}
.stButton > button[kind="secondary"]:hover {{
    background-color: #E8F2F2 !important;
    color: {GGH_TEAL_HOVER} !important;
    border-color: {GGH_TEAL_HOVER} !important;
}}

/* KPI section labels */
.kpi-section-label {{
    text-transform: uppercase;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #526077;
    margin: 12px 0 6px 2px;
}}

/* KPI cards */
.kpi-card {{
    border-left: 4px solid;
    padding: 12px 14px;
    border-radius: 6px;
    background: #F8FAFC;
    min-height: 92px;
    margin-bottom: 6px;
}}
.kpi-card .kpi-label {{
    text-transform: uppercase;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: #475569;
}}
.kpi-card .kpi-value {{
    font-size: 26px;
    font-weight: 700;
    margin-top: 4px;
    line-height: 1.1;
}}
.kpi-card .kpi-sub {{
    font-size: 11.5px;
    color: #64748B;
    margin-top: 4px;
}}

/* Brand-tinted teal (primary) + status variants */
.kpi-blue   {{ background: #E8F2F2; border-color: {GGH_TEAL}; }}
.kpi-blue   .kpi-value {{ color: {GGH_TEAL}; }}
.kpi-green  {{ background: #ECF6EE; border-color: #2E7D32; }}
.kpi-green  .kpi-value {{ color: #2E7D32; }}
.kpi-red    {{ background: #FBECEC; border-color: #C62828; }}
.kpi-red    .kpi-value {{ color: #C62828; }}
.kpi-amber  {{ background: #FDF6E3; border-color: #B8860B; }}
.kpi-amber  .kpi-value {{ color: #B8860B; }}
.kpi-orange {{ background: #FDF1E3; border-color: #EF6C00; }}
.kpi-orange .kpi-value {{ color: #EF6C00; }}
.kpi-gray   {{ background: #F1F3F5; border-color: #6B7280; }}
.kpi-gray   .kpi-value {{ color: #374151; }}
.kpi-purple {{ background: #F3EEF7; border-color: #6A1B9A; }}
.kpi-purple .kpi-value {{ color: #6A1B9A; }}

/* ----- Clickable KPI tiles -----
   Any Streamlit container keyed "tile_*" overlays an invisible button
   on top of its KPI card, so the whole card acts as a drill-down button. */
[class*="st-key-tile_"] {{
    position: relative;
}}
[class*="st-key-tile_"] .kpi-card {{
    cursor: pointer;
    transition: transform 0.12s ease, box-shadow 0.12s ease;
    position: relative;
}}
[class*="st-key-tile_"] .kpi-card::after {{
    content: "↗";
    position: absolute;
    top: 8px;
    right: 12px;
    color: #94A3B8;
    font-size: 15px;
    opacity: 0.55;
    pointer-events: none;
}}
[class*="st-key-tile_"] .kpi-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 14px rgba(14, 59, 59, 0.12);
}}
[class*="st-key-tile_"] .stButton {{
    position: absolute !important;
    inset: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    z-index: 10 !important;
}}
[class*="st-key-tile_"] .stButton > button {{
    width: 100% !important;
    height: 100% !important;
    min-height: 100% !important;
    opacity: 0 !important;
    background: transparent !important;
    border: 0 !important;
    padding: 0 !important;
    cursor: pointer !important;
    color: transparent !important;
    border-radius: 6px !important;
}}
[class*="st-key-tile_"] .stButton > button:focus-visible {{
    outline: 2px solid {GGH_TEAL} !important;
    opacity: 1 !important;
    background: transparent !important;
}}
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# Data loading
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner="Loading SuperBill + Revenue Tracker from Azure…")
def load_everything():
    sb_raw, sb_info = data_loader.load_superbill()
    tr_raw, tr_info = data_loader.load_tracker()
    df_claims, df_orphan, dup_info = data_processor.build_claims_dataframe(
        sb_raw, tr_raw,
        year_hint=data_loader.year_hint_from_superbill_blob(),
    )
    return {
        "df_claims": df_claims,
        "df_orphan": df_orphan,
        "dup_info":  dup_info,
        "sb_info":   sb_info,
        "tr_info":   tr_info,
        "loaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


try:
    data = load_everything()
except Exception as e:
    st.error(f"Could not load data from Azure Blob Storage:\n\n{e}")
    st.stop()

df_claims = data["df_claims"]
df_orphan = data["df_orphan"]
dup_info  = data["dup_info"]
sb_info   = data["sb_info"]
tr_info   = data["tr_info"]


# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------
hdr_left, hdr_right = st.columns([6, 1], vertical_alignment="center")
with hdr_left:
    st.markdown(f"""
<div class="gg-header">
    <div class="gg-accent"></div>
    <div class="gg-logo-wrap">
        <img src="{GGH_LOGO_URL}" alt="GroundGame.Health">
    </div>
    <div class="gg-title">
        <h1>Revenue Cycle Dashboard</h1>
        <div class="meta">
            Last refreshed: <b>{data['loaded_at']}</b> &nbsp;·&nbsp;
            SuperBill: <b>{sb_info['filename']}</b> ({sb_info['modified']}) &nbsp;·&nbsp;
            Revenue Tracker: <b>{tr_info['filename']}</b> ({tr_info['modified']})
        </div>
    </div>
</div>
""", unsafe_allow_html=True)
with hdr_right:
    if st.button("↻  Refresh Data", use_container_width=True, type="primary",
                 help="Re-pull SuperBill + Revenue Tracker from Azure Blob Storage"):
        load_everything.clear()
        st.rerun()


# -----------------------------------------------------------------------------
# Sidebar filters
# -----------------------------------------------------------------------------
options = metrics_mod.filter_options(df_claims)

def _opt_select(label, values, key, formatter=None):
    choices = ["All"] + list(values)
    picked = st.sidebar.selectbox(
        label, choices, index=0, key=key,
        format_func=formatter if formatter else str,
    )
    return None if picked == "All" else picked

st.sidebar.header("Filters")

month_values = [m["value"] for m in options["billing_months"]]
month_labels = {m["value"]: m["label"] for m in options["billing_months"]}
billing_month = _opt_select(
    "Billing Month", month_values, "f_month",
    formatter=lambda v: "All" if v == "All" else month_labels.get(v, v),
)
provider = _opt_select("Provider (NPI)",     options["providers"],            "f_provider")
payer    = _opt_select("Payer",              options["payers"],               "f_payer")
status   = _opt_select("Normalized Status",  options["statuses"],             "f_status")
group    = _opt_select("Group Type",         options["group_types"],          "f_group")
entity   = _opt_select("Contracting Entity", options["contracting_entities"], "f_entity")
proc     = _opt_select("Procedure Code",     options["procedure_codes"],      "f_proc")

filters = {
    "billing_month":      billing_month,
    "provider":           provider,
    "payer":              payer,
    "status":             status,
    "group_type":         group,
    "contracting_entity": entity,
    "procedure_code":     proc,
}

st.sidebar.divider()
st.sidebar.caption(
    "**Data source:** Azure Blob Storage. "
    "Upload replacement files to the configured container and click "
    "**Refresh Data** at the top to re-pull."
)


# -----------------------------------------------------------------------------
# Compute metrics
# -----------------------------------------------------------------------------
fdf = metrics_mod.apply_filters(df_claims, filters)

kpis     = metrics_mod.calculate_kpis(fdf)
monthly  = metrics_mod.calculate_monthly_metrics(fdf)
status_b = metrics_mod.status_breakdown(fdf)
aging    = metrics_mod.aging_breakdown(fdf)
payer_m  = metrics_mod.calculate_payer_metrics(fdf)
prov_m   = metrics_mod.calculate_provider_metrics(fdf)
dq       = metrics_mod.calculate_data_quality(fdf, df_orphan, dup_info)
summary  = metrics_mod.generate_executive_summary(fdf, kpis, monthly, payer_m, dq)


# -----------------------------------------------------------------------------
# Drill-down mapping — maps a KPI key → (display label, filter function)
# -----------------------------------------------------------------------------
DRILLS = {
    "paid":          ("Paid Claims",         lambda d: d[d["is_paid"]]),
    "denied":        ("Denied Claims",       lambda d: d[d["is_denied"]]),
    "pending":       ("Pending Claims",      lambda d: d[d["is_pending"]]),
    "resubmitted":   ("Resubmitted Claims",
                      lambda d: d[d["claim_status_normalized"].eq("Resubmitted")]),
    "not_submitted": ("Not Submitted",       lambda d: d[~d["in_tracker"]]),
    "outstanding":   ("Outstanding Claims",  lambda d: d[d["is_outstanding"]]),
    "declined":      ("Declined at Provider",lambda d: d[d["is_declined_at_provider"]]),
}


# -----------------------------------------------------------------------------
# Executive summary
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.markdown("##### EXECUTIVE SUMMARY")
    for line in summary:
        st.markdown(f"- {line}")


# -----------------------------------------------------------------------------
# KPI tiles — grouped, color-coded, with drill-down buttons on outcome tiles
# -----------------------------------------------------------------------------
def kpi_card(label: str, value: str, color: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (f'<div class="kpi-card kpi-{color}">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'{sub_html}</div>')

def static_kpi(column, label: str, value: str, color: str, sub: str = ""):
    """A plain informational tile — not clickable."""
    column.markdown(kpi_card(label, value, color, sub), unsafe_allow_html=True)

def clickable_kpi(column, drill_key: str, label: str, value: str,
                  color: str, sub: str = ""):
    """A tile the user can click to drill into the raw rows for that bucket."""
    with column:
        with st.container(key=f"tile_{drill_key}"):
            st.markdown(kpi_card(label, value, color, sub),
                        unsafe_allow_html=True)
            if st.button(f"View {label}", key=f"btn_{drill_key}",
                         use_container_width=True):
                st.session_state["drill"] = drill_key
                st.rerun()

with st.container(border=True):
    st.markdown("##### KPI OVERVIEW")

    # VOLUME
    st.markdown('<div class="kpi-section-label">VOLUME</div>',
                unsafe_allow_html=True)
    v = st.columns(4)
    static_kpi(v[0], "Total SuperBills",
               f"{kpis['total_superbills']:,}", "blue")
    static_kpi(v[1], "Total Charge Amount",
               f"${kpis['total_charge_amount']:,.2f}", "blue")
    static_kpi(v[2], "Claims Submitted",
               f"{kpis['total_submitted']:,}", "blue",
               f"Submission Rate: {kpis['submission_rate']:.1f}%")
    clickable_kpi(v[3], "not_submitted", "Not Submitted",
                  f"{kpis['not_submitted_claims']:,}", "orange")

    # CLAIM OUTCOMES
    st.markdown('<div class="kpi-section-label">CLAIM OUTCOMES</div>',
                unsafe_allow_html=True)
    o = st.columns(4)
    clickable_kpi(o[0], "paid", "Paid Claims",
                  f"{kpis['paid_claims']:,}", "green",
                  f"Paid Rate: {kpis['paid_rate']:.1f}%")
    clickable_kpi(o[1], "denied", "Denied Claims",
                  f"{kpis['denied_claims']:,}", "red",
                  f"Denial Rate: {kpis['denial_rate']:.1f}%")
    clickable_kpi(o[2], "pending", "Pending Claims",
                  f"{kpis['pending_claims']:,}", "gray")
    clickable_kpi(o[3], "resubmitted", "Resubmitted",
                  f"{kpis['resubmitted_claims']:,}", "purple")

    # FINANCIAL & FOLLOW-UP
    st.markdown('<div class="kpi-section-label">FINANCIAL &amp; FOLLOW-UP</div>',
                unsafe_allow_html=True)
    f = st.columns(4)
    static_kpi(f[0], "Charges — Paid Claims",
               f"${kpis['charges_paid']:,.2f}", "green",
               "Not revenue collected")
    static_kpi(f[1], "Charges — Denied",
               f"${kpis['charges_denied']:,.2f}", "red")
    clickable_kpi(f[2], "outstanding", "Outstanding Charges",
                  f"${kpis['outstanding_charge']:,.2f}", "amber",
                  "Pending / Denied / Resubmitted")
    clickable_kpi(f[3], "declined", "Declined at Provider",
                  f"{kpis['declined_at_provider_claims']:,}", "gray",
                  f"${kpis['charges_declined_at_provider']:,.2f}")

    with st.expander("KPI definitions"):
        st.markdown("""
- **Total SuperBills** — count of SuperBill rows.
- **Total Charge Amount** — sum of Charge Amount. **Not** collected revenue.
- **Claims Submitted** — tracker status is Paid / Denied / Pending / Resubmitted / Rejected.
- **Submission Rate** — Claims Submitted ÷ Total SuperBills.
- **Paid / Denial Rate** — of submitted claims only.
- **Not Submitted** — SuperBills with no matching Revenue Tracker row.
- **Outstanding Charges** — charges on submitted claims that are not Paid and not Rejected.
- **Declined at Provider** — provider chose not to bill; not counted as Not Submitted.
""")


# -----------------------------------------------------------------------------
# Drill-down panel — shows filtered rows for whichever KPI was clicked
# -----------------------------------------------------------------------------
drill_key = st.session_state.get("drill")
if drill_key and drill_key in DRILLS:
    label, filter_fn = DRILLS[drill_key]
    drill_df = filter_fn(fdf)
    with st.container(border=True):
        hc_left, hc_right = st.columns([5, 1])
        hc_left.markdown(f"### 🔍 Drill-down: {label} "
                         f"<span style='color:#64748B;font-size:14px;'>"
                         f"({len(drill_df):,} rows, "
                         f"respecting current sidebar filters)</span>",
                         unsafe_allow_html=True)
        if hc_right.button("✕ Close", key="drill_close",
                           use_container_width=True):
            st.session_state["drill"] = None
            st.rerun()

        if len(drill_df) == 0:
            st.info("No claims match this category under the current filters.")
        else:
            detail_df = metrics_mod.detail_dataframe(drill_df)
            st.dataframe(detail_df, use_container_width=True,
                         hide_index=True, height=420)

            buf = StringIO()
            w = csv.writer(buf)
            w.writerow(list(detail_df.columns))
            w.writerows(detail_df.itertuples(index=False, name=None))
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                f"⬇️ Download {label} as CSV",
                data=buf.getvalue(),
                file_name=f"{drill_key}_{stamp}.csv",
                mime="text/csv",
                key="drill_dl",
            )


# -----------------------------------------------------------------------------
# Tabs
# -----------------------------------------------------------------------------
tab_trends, tab_mix, tab_payer, tab_prov, tab_detail, tab_dq = st.tabs([
    "Trends", "Status & Aging", "Payers", "Providers", "Claim Detail", "Data Quality",
])

with tab_trends:
    st.plotly_chart(charts.monthly_volume(monthly), use_container_width=True)
    st.plotly_chart(charts.monthly_rates(monthly),  use_container_width=True)

with tab_mix:
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.status_donut(status_b), use_container_width=True)
    with c2:
        st.plotly_chart(charts.aging_bars(aging), use_container_width=True)

with tab_payer:
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.top_payers_bar(payer_m["top_payers"]),
                        use_container_width=True)
    with c2:
        st.plotly_chart(charts.denial_by_payer_bar(payer_m["denial_by_payer"]),
                        use_container_width=True)
    st.markdown("##### Payer breakdown")
    st.dataframe(pd.DataFrame(payer_m["table"]),
                 use_container_width=True, hide_index=True)

with tab_prov:
    st.markdown("##### Provider breakdown (NPI-only display)")
    st.dataframe(pd.DataFrame(prov_m),
                 use_container_width=True, hide_index=True)

with tab_detail:
    st.markdown("##### Claim detail")
    search = st.text_input(
        "Search (SuperBill ID, Member Name, Claim #, Provider, Payer)",
        key="detail_search",
    ).strip().lower()

    detail_df = metrics_mod.detail_dataframe(fdf)
    if search:
        search_cols = [c for c in [
            "SuperBill ID", "Member Name", "Claim #", "Provider", "Payer",
        ] if c in detail_df.columns]
        if search_cols:
            mask = None
            for c in search_cols:
                m = detail_df[c].astype(str).str.lower().str.contains(search, na=False)
                mask = m if mask is None else (mask | m)
            if mask is not None:
                detail_df = detail_df[mask]

    st.caption(f"{len(detail_df):,} rows")
    st.dataframe(detail_df, use_container_width=True, hide_index=True, height=520)

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(list(detail_df.columns))
    w.writerows(detail_df.itertuples(index=False, name=None))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        "⬇️ Download filtered claims as CSV",
        data=buf.getvalue(),
        file_name=f"claims_{stamp}.csv",
        mime="text/csv",
    )

with tab_dq:
    d1, d2, d3 = st.columns(3)
    d1.markdown(kpi_card("Missing from Tracker",
                         f"{dq['missing_from_tracker']:,}", "orange"),
                unsafe_allow_html=True)
    d2.markdown(kpi_card("Tracker Rows w/o SuperBill",
                         f"{dq['tracker_rows_without_superbill']:,}", "gray"),
                unsafe_allow_html=True)
    d3.markdown(kpi_card("Submitted w/o Claim #",
                         f"{dq['submitted_without_claim_number']:,}", "red"),
                unsafe_allow_html=True)

    d4, d5, d6 = st.columns(3)
    d4.markdown(kpi_card("Missing Status (in Tracker)",
                         f"{dq['missing_status']:,}", "amber"),
                unsafe_allow_html=True)
    d5.markdown(kpi_card("Missing Provider",
                         f"{dq['missing_provider']:,}", "gray"),
                unsafe_allow_html=True)
    d6.markdown(kpi_card("Missing Payer",
                         f"{dq['missing_payer']:,}", "gray"),
                unsafe_allow_html=True)

    d7, _, _ = st.columns(3)
    d7.markdown(kpi_card("Missing Charge Amount",
                         f"{dq['missing_charge_amount']:,}", "amber"),
                unsafe_allow_html=True)