"""
Revenue Cycle Dashboard — Streamlit edition.

Replaces the Flask + Plotly.js version. Reads SuperBill + Revenue Tracker
Excel files from Azure Blob Storage (manual upload — click Refresh Data
after replacing the blobs). All business rules and KPIs match the Flask
version exactly; only the loader and UI changed.
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
# Data loading (cached). Clearing the cache = re-fetching from Azure Blob.
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


# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------
st.title("GGH Revenue Cycle Dashboard")
st.caption(
    "Claim-lifecycle KPIs built from SuperBill + Revenue Tracker. "
    "Charge Amount is NOT collected revenue."
)

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

head_a, head_b, head_c, head_d = st.columns([2, 2, 2, 1])
with head_a:
    st.markdown(f"**SuperBill**  \n`{sb_info['filename']}`  \n"
                f"Modified: {sb_info['modified']} · {sb_info['rows']:,} rows")
with head_b:
    st.markdown(f"**Revenue Tracker**  \n`{tr_info['filename']}`  \n"
                f"Modified: {tr_info['modified']} · {tr_info['rows']:,} rows")
with head_c:
    st.markdown(f"**Dashboard loaded**  \n{data['loaded_at']}")
with head_d:
    if st.button("🔄 Refresh Data", use_container_width=True):
        load_everything.clear()
        st.rerun()

st.divider()


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

provider = _opt_select("Provider (NPI)",       options["providers"],            "f_provider")
payer    = _opt_select("Payer",                options["payers"],               "f_payer")
status   = _opt_select("Normalized Status",    options["statuses"],             "f_status")
group    = _opt_select("Group Type",           options["group_types"],          "f_group")
entity   = _opt_select("Contracting Entity",   options["contracting_entities"], "f_entity")
proc     = _opt_select("Procedure Code",       options["procedure_codes"],      "f_proc")

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
# Apply filters, compute metrics
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
st.subheader("Executive Summary")
for line in summary:
    st.markdown(f"- {line}")


# -----------------------------------------------------------------------------
# KPI row
# -----------------------------------------------------------------------------
st.subheader("Key Metrics")
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total SuperBills",   f"{kpis['total_superbills']:,}")
k2.metric("Total Charges",      f"${kpis['total_charge_amount']:,.2f}")
k3.metric("Submission Rate",    f"{kpis['submission_rate']:.1f}%",
          help=f"{kpis['total_submitted']:,} submitted / "
               f"{kpis['total_superbills']:,} SuperBills")
k4.metric("Paid Rate",          f"{kpis['paid_rate']:.1f}%",
          help=f"{kpis['paid_claims']:,} paid / "
               f"{kpis['total_submitted']:,} submitted")
k5.metric("Denial Rate",        f"{kpis['denial_rate']:.1f}%",
          help=f"{kpis['denied_claims']:,} denied / "
               f"{kpis['total_submitted']:,} submitted")

k6, k7, k8, k9, k10 = st.columns(5)
k6.metric("Pending Claims",      f"{kpis['pending_claims']:,}")
k7.metric("Resubmitted",         f"{kpis['resubmitted_claims']:,}")
k8.metric("Rejected",            f"{kpis['rejected_claims']:,}")
k9.metric("Not Submitted",       f"{kpis['not_submitted_claims']:,}",
          help="SuperBills without a Revenue Tracker row.")
k10.metric("Outstanding Charges", f"${kpis['outstanding_charge']:,.2f}",
           help="Submitted claims not Paid and not Rejected.")


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
        st.plotly_chart(charts.aging_bars(aging),      use_container_width=True)

with tab_payer:
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.top_payers_bar(payer_m["top_payers"]),
                        use_container_width=True)
    with c2:
        st.plotly_chart(charts.denial_by_payer_bar(payer_m["denial_by_payer"]),
                        use_container_width=True)
    st.markdown("##### Payer breakdown")
    st.dataframe(
        pd.DataFrame(payer_m["table"]),
        use_container_width=True, hide_index=True,
    )

with tab_prov:
    st.markdown("##### Provider breakdown (NPI-only display)")
    st.dataframe(
        pd.DataFrame(prov_m),
        use_container_width=True, hide_index=True,
    )

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
    d1.metric("Missing from Tracker",            f"{dq['missing_from_tracker']:,}")
    d2.metric("Tracker rows w/o SuperBill",      f"{dq['tracker_rows_without_superbill']:,}")
    d3.metric("Submitted w/o Claim #",           f"{dq['submitted_without_claim_number']:,}")

    d4, d5, d6 = st.columns(3)
    d4.metric("Missing Status (in Tracker)",     f"{dq['missing_status']:,}")
    d5.metric("Missing Provider",                f"{dq['missing_provider']:,}")
    d6.metric("Missing Payer",                   f"{dq['missing_payer']:,}")

    d7, d8, d9 = st.columns(3)
    d7.metric("Missing Charge Amount",           f"{dq['missing_charge_amount']:,}")
    d8.metric("Dup SB IDs (SuperBill file)",     f"{dq['duplicate_superbill_ids_in_sb']:,}")
    d9.metric("Dup SB IDs (Tracker file)",       f"{dq['duplicate_superbill_ids_in_tr']:,}")

    if dq["duplicate_superbill_list_sb"]:
        st.markdown("##### Duplicates in SuperBill")
        st.dataframe(pd.DataFrame(dq["duplicate_superbill_list_sb"]),
                     use_container_width=True, hide_index=True)
    if dq["duplicate_superbill_list_tr"]:
        st.markdown("##### Duplicates in Revenue Tracker")
        st.dataframe(pd.DataFrame(dq["duplicate_superbill_list_tr"]),
                     use_container_width=True, hide_index=True)
