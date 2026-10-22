"""
Revenue Cycle Dashboard — Streamlit edition.
Branded header + color-coded KPI tiles matching the Flask original.
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
# Custom styling — dark header, grouped color-coded KPI tiles.
# -----------------------------------------------------------------------------
st.markdown("""
<style>
/* Dark header strip */
.gg-header {
    background: #0F172A;
    color: #FFFFFF;
    padding: 16px 22px;
    border-radius: 8px;
    margin-bottom: 14px;
}
.gg-header h1 { color: #FFFFFF; margin: 0; font-size: 22px; font-weight: 700; }
.gg-header .meta { color: #94A3B8; font-size: 12.5px; margin-top: 6px; }
.gg-header .meta b { color: #E2E8F0; }

/* KPI section labels */
.kpi-section-label {
    text-transform: uppercase;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    color: #64748B;
    margin: 14px 0 6px 2px;
}

/* KPI cards */
.kpi-card {
    border-left: 4px solid;
    padding: 12px 14px;
    border-radius: 6px;
    background: #F8FAFC;
    min-height: 92px;
    margin-bottom: 10px;
}
.kpi-card .kpi-label {
    text-transform: uppercase;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: #475569;
}
.kpi-card .kpi-value {
    font-size: 26px;
    font-weight: 700;
    margin-top: 4px;
    line-height: 1.1;
}
.kpi-card .kpi-sub {
    font-size: 11.5px;
    color: #64748B;
    margin-top: 4px;
}

/* Color variants */
.kpi-blue   { background: #EFF4FB; border-color: #1565C0; }
.kpi-blue   .kpi-value { color: #1565C0; }
.kpi-green  { background: #ECF6EE; border-color: #2E7D32; }
.kpi-green  .kpi-value { color: #2E7D32; }
.kpi-red    { background: #FBECEC; border-color: #C62828; }
.kpi-red    .kpi-value { color: #C62828; }
.kpi-amber  { background: #FDF6E3; border-color: #B8860B; }
.kpi-amber  .kpi-value { color: #B8860B; }
.kpi-orange { background: #FDF1E3; border-color: #EF6C00; }
.kpi-orange .kpi-value { color: #EF6C00; }
.kpi-gray   { background: #F1F3F5; border-color: #6B7280; }
.kpi-gray   .kpi-value { color: #374151; }
.kpi-purple { background: #F3EEF7; border-color: #6A1B9A; }
.kpi-purple .kpi-value { color: #6A1B9A; }
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
# Dark header + refresh button
# -----------------------------------------------------------------------------
hdr_left, hdr_right = st.columns([6, 1])
with hdr_left:
    st.markdown(f"""
<div class="gg-header">
    <h1>Revenue Cycle Dashboard</h1>
    <div class="meta">
        Last refreshed: <b>{data['loaded_at']}</b> &nbsp;·&nbsp;
        SuperBill: <b>{sb_info['filename']}</b> ({sb_info['modified']}) &nbsp;·&nbsp;
        Revenue Tracker: <b>{tr_info['filename']}</b> ({tr_info['modified']})
    </div>
</div>
""", unsafe_allow_html=True)
with hdr_right:
    st.write("")
    if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
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
    "**Refresh Data** at the top of the page to re-pull."
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
# Executive summary
# -----------------------------------------------------------------------------
with st.container(border=True):
    st.markdown("##### EXECUTIVE SUMMARY")
    for line in summary:
        st.markdown(f"- {line}")


# -----------------------------------------------------------------------------
# KPI tiles — grouped and color-coded
# -----------------------------------------------------------------------------
def kpi_card(label: str, value: str, color: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return (f'<div class="kpi-card kpi-{color}">'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'{sub_html}</div>')

with st.container(border=True):
    st.markdown("##### KPI OVERVIEW")

    st.markdown('<div class="kpi-section-label">VOLUME</div>', unsafe_allow_html=True)
    v = st.columns(4)
    v[0].markdown(kpi_card("Total SuperBills",
                           f"{kpis['total_superbills']:,}", "blue"),
                  unsafe_allow_html=True)
    v[1].markdown(kpi_card("Total Charge Amount",
                           f"${kpis['total_charge_amount']:,.2f}", "blue"),
                  unsafe_allow_html=True)
    v[2].markdown(kpi_card("Claims Submitted",
                           f"{kpis['total_submitted']:,}", "blue",
                           f"Submission Rate: {kpis['submission_rate']:.1f}%"),
                  unsafe_allow_html=True)
    v[3].markdown(kpi_card("Not Submitted",
                           f"{kpis['not_submitted_claims']:,}", "orange"),
                  unsafe_allow_html=True)

    st.markdown('<div class="kpi-section-label">CLAIM OUTCOMES</div>',
                unsafe_allow_html=True)
    o = st.columns(4)
    o[0].markdown(kpi_card("Paid Claims",
                           f"{kpis['paid_claims']:,}", "green",
                           f"Paid Rate: {kpis['paid_rate']:.1f}%"),
                  unsafe_allow_html=True)
    o[1].markdown(kpi_card("Denied Claims",
                           f"{kpis['denied_claims']:,}", "red",
                           f"Denial Rate: {kpis['denial_rate']:.1f}%"),
                  unsafe_allow_html=True)
    o[2].markdown(kpi_card("Pending Claims",
                           f"{kpis['pending_claims']:,}", "gray"),
                  unsafe_allow_html=True)
    o[3].markdown(kpi_card("Resubmitted",
                           f"{kpis['resubmitted_claims']:,}", "purple"),
                  unsafe_allow_html=True)

    st.markdown('<div class="kpi-section-label">FINANCIAL &amp; FOLLOW-UP</div>',
                unsafe_allow_html=True)
    f = st.columns(4)
    f[0].markdown(kpi_card("Charges — Paid Claims",
                           f"${kpis['charges_paid']:,.2f}", "green",
                           "Not revenue collected"),
                  unsafe_allow_html=True)
    f[1].markdown(kpi_card("Charges — Denied",
                           f"${kpis['charges_denied']:,.2f}", "red"),
                  unsafe_allow_html=True)
    f[2].markdown(kpi_card("Outstanding Charges",
                           f"${kpis['outstanding_charge']:,.2f}", "amber",
                           "Pending / Denied / Resubmitted"),
                  unsafe_allow_html=True)
    f[3].markdown(kpi_card("Declined at Provider",
                           f"{kpis['declined_at_provider_claims']:,}", "gray",
                           f"${kpis['charges_declined_at_provider']:,.2f}"),
                  unsafe_allow_html=True)

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

    d7, d8, d9 = st.columns(3)
    d7.markdown(kpi_card("Missing Charge Amount",
                         f"{dq['missing_charge_amount']:,}", "amber"),
                unsafe_allow_html=True)
    d8.markdown(kpi_card("Dup SB IDs (SuperBill)",
                         f"{dq['duplicate_superbill_ids_in_sb']:,}", "red"),
                unsafe_allow_html=True)
    d9.markdown(kpi_card("Dup SB IDs (Tracker)",
                         f"{dq['duplicate_superbill_ids_in_tr']:,}", "red"),
                unsafe_allow_html=True)

    if dq["duplicate_superbill_list_sb"]:
        st.markdown("##### Duplicates in SuperBill")
        st.dataframe(pd.DataFrame(dq["duplicate_superbill_list_sb"]),
                     use_container_width=True, hide_index=True)
    if dq["duplicate_superbill_list_tr"]:
        st.markdown("##### Duplicates in Revenue Tracker")
        st.dataframe(pd.DataFrame(dq["duplicate_superbill_list_tr"]),
                     use_container_width=True, hide_index=True)