"""
Compute KPIs, chart data, filter options, data-quality counts,
executive summary, and detail-table rows from the unified df_claims.
"""
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd

import config


# -----------------------------------------------------------------------------
# Filter application
# -----------------------------------------------------------------------------
def apply_filters(df: pd.DataFrame, filters: Optional[dict]) -> pd.DataFrame:
    if not filters:
        return df
    out = df
    bm = filters.get("billing_month")
    if bm and bm not in (None, "", "All"):
        try:
            target = pd.Timestamp(bm).normalize()
            out = out[out["billing_month_key"] == target]
        except (ValueError, TypeError):
            pass

    for key, col in [
        ("provider",           "provider_display"),
        ("payer",              "payer_display"),
        ("status",             "claim_status_normalized"),
        ("group_type",         "Group Type"),
        ("contracting_entity", "Contracting/Billing Entity"),
        ("procedure_code",     "Procedure Code"),
    ]:
        v = filters.get(key)
        if v in (None, "", "All"):
            continue
        if col not in out.columns:
            continue
        out = out[out[col] == v]
    return out


# -----------------------------------------------------------------------------
# Filter options
# -----------------------------------------------------------------------------
def _unique_sorted(series) -> List:
    vals = [v for v in series.dropna().unique().tolist() if str(v).strip() != ""]
    try:
        return sorted(vals, key=lambda x: str(x).lower())
    except Exception:
        return vals


def filter_options(df: pd.DataFrame) -> dict:
    months = df["billing_month_key"].dropna().unique()
    months_sorted = sorted(months)
    return {
        "billing_months": [
            {"value": str(pd.Timestamp(m)), "label": pd.Timestamp(m).strftime("%B %Y")}
            for m in months_sorted
        ],
        "providers":            _unique_sorted(df["provider_display"]),
        "payers":               _unique_sorted(df["payer_display"]),
        "statuses":             _unique_sorted(df["claim_status_normalized"]),
        "group_types":          _unique_sorted(df["Group Type"]) if "Group Type" in df.columns else [],
        "contracting_entities": _unique_sorted(df["Contracting/Billing Entity"]) if "Contracting/Billing Entity" in df.columns else [],
        "procedure_codes":      _unique_sorted(df["Procedure Code"]) if "Procedure Code" in df.columns else [],
    }


def _safe_div(n, d):
    return (n / d) if d else 0.0


def calculate_kpis(df: pd.DataFrame) -> dict:
    s = df["claim_status_normalized"]

    # Total SuperBills: distinct (Billing Provider NPI, SuperBill ID) pairs.
    # Falls back to row count when the NPI column isn't present.
    if "Billing Provider NPI" in df.columns:
        total_superbills_distinct = int(
            df.drop_duplicates(
                subset=["Billing Provider NPI", "superbill_id_clean"]
            ).shape[0]
        )
    else:
        total_superbills_distinct = int(len(df))

    total_billable_items = int(len(df))
    total_charge = float(df["charge_amount_clean"].sum(skipna=True))

    submitted            = int(df["is_submitted"].sum())
    paid                 = int(df["is_paid"].sum())
    denied               = int(df["is_denied"].sum())
    pending              = int(df["is_pending"].sum())
    resubmitted          = int(s.eq("Resubmitted").sum())
    rejected             = int(df["is_rejected"].sum())
    yet_to_submit        = int((~df["in_tracker"]).sum())
    declined_at_provider = int(df["is_declined_at_provider"].sum())

    # Outstanding split:
    #   Pending       = in tracker, status Pending  (payer processing — normal)
    #   Needs Rework  = in tracker, not Paid / not Denied / not Pending /
    #                   not Declined-at-Provider  (rejected, missing status, resubmitted)
    #   Yet to Submit = NOT in tracker (not yet entered pipeline)
    outstanding_pending_mask = df["in_tracker"] & df["is_pending"]
    outstanding_rework_mask  = (
        df["in_tracker"] & ~df["is_paid"] & ~df["is_denied"]
        & ~df["is_pending"] & ~df["is_declined_at_provider"]
    )
    outstanding_sub_mask = df["in_tracker"] & ~df["is_paid"] & ~df["is_denied"]

    outstanding_pending_count   = int(outstanding_pending_mask.sum())
    outstanding_pending_charges = float(
        df.loc[outstanding_pending_mask, "charge_amount_clean"].sum(skipna=True)
    )
    outstanding_rework_count    = int(outstanding_rework_mask.sum())
    outstanding_rework_charges  = float(
        df.loc[outstanding_rework_mask, "charge_amount_clean"].sum(skipna=True)
    )
    outstanding_sub_count   = int(outstanding_sub_mask.sum())
    outstanding_sub_charges = float(
        df.loc[outstanding_sub_mask, "charge_amount_clean"].sum(skipna=True)
    )
    yet_to_submit_charges = float(
        df.loc[~df["in_tracker"], "charge_amount_clean"].sum(skipna=True)
    )

    # Oldest outstanding claim (days since Superbill Generated) for triage
    submitted_outstanding_mask = (
        df["in_tracker"] & ~df["is_paid"] & ~df["is_denied"] & ~df["is_declined_at_provider"]
    )
    if "days_since_generated" in df.columns:
        _days = df.loc[submitted_outstanding_mask, "days_since_generated"].dropna()
        oldest_outstanding_days = int(_days.max()) if len(_days) > 0 else 0
    else:
        oldest_outstanding_days = 0

    # Procedure-code unit economics for G0019 / G0022
    def _proc_stats(code: str):
        if "Procedure Code" not in df.columns:
            return 0, 0.0, 0.0
        mask = df["Procedure Code"].astype(str).str.strip().str.upper() == code
        cnt = int(mask.sum())
        total = float(df.loc[mask, "charge_amount_clean"].sum(skipna=True))
        avg = (total / cnt) if cnt > 0 else 0.0
        return cnt, total, avg

    g0019_count, g0019_charges, g0019_avg = _proc_stats("G0019")
    g0022_count, g0022_charges, g0022_avg = _proc_stats("G0022")

    return {
        # Volume
        "total_superbills":            total_superbills_distinct,
        "total_billable_items":        total_billable_items,
        "total_charge_amount":         round(total_charge, 2),
        "total_submitted":             submitted,
        "submission_rate":             round(100 * _safe_div(submitted, total_billable_items), 2),
        "yet_to_submit_count":         yet_to_submit,

        # Outcomes
        "paid_claims":                 paid,
        "paid_rate":                   round(100 * _safe_div(paid, submitted), 2),
        "denied_claims":               denied,
        "denial_rate":                 round(100 * _safe_div(denied, submitted), 2),
        "pending_claims":              pending,
        "resubmitted_claims":          resubmitted,
        "rejected_claims":             rejected,
        "declined_at_provider_claims": declined_at_provider,

        # Financial
        "charges_paid":                round(float(df.loc[df["is_paid"],   "charge_amount_clean"].sum(skipna=True)), 2),
        "charges_denied":              round(float(df.loc[df["is_denied"], "charge_amount_clean"].sum(skipna=True)), 2),
        "charges_pending":             round(float(df.loc[df["is_pending"],"charge_amount_clean"].sum(skipna=True)), 2),
        "charges_submitted":           round(float(df.loc[df["is_submitted"], "charge_amount_clean"].sum(skipna=True)), 2),
        "outstanding_pending_count":   outstanding_pending_count,
        "outstanding_pending_charges": round(outstanding_pending_charges, 2),
        "outstanding_rework_count":    outstanding_rework_count,
        "outstanding_rework_charges":  round(outstanding_rework_charges, 2),
        "outstanding_sub_count":       outstanding_sub_count,
        "outstanding_sub_charges":     round(outstanding_sub_charges, 2),
        "yet_to_submit_charges":       round(yet_to_submit_charges, 2),
        "charges_declined_at_provider":round(float(df.loc[df["is_declined_at_provider"], "charge_amount_clean"].sum(skipna=True)), 2),

        # Operational signal
        "oldest_outstanding_days":     oldest_outstanding_days,

        # Procedure-code unit economics (G0019 / G0022)
        "g0019_count":   g0019_count,
        "g0019_charges": round(g0019_charges, 2),
        "g0019_avg":     round(g0019_avg, 2),
        "g0022_count":   g0022_count,
        "g0022_charges": round(g0022_charges, 2),
        "g0022_avg":     round(g0022_avg, 2),

        # Back-compat aliases
        "not_submitted_claims":        yet_to_submit,
        "missing_from_tracker":        yet_to_submit,
        "outstanding_charge":          round(outstanding_sub_charges + yet_to_submit_charges, 2),
        "charges_not_submitted":       round(yet_to_submit_charges, 2),
    }


def calculate_monthly_metrics(df: pd.DataFrame) -> dict:
    empty = {"months": [], "labels": [], "sb_count": [], "charge_amount": [],
             "status_breakdown": {}, "submission_rate": [],
             "paid_rate": [], "denial_rate": []}
    if df.empty or df["billing_month_key"].dropna().empty:
        return empty

    d = df.dropna(subset=["billing_month_key"]).copy()
    d["_m"] = pd.to_datetime(d["billing_month_key"])
    grp = d.groupby("_m", sort=True)

    month_keys = list(grp.groups.keys())
    months = [m.strftime("%Y-%m-%d") for m in month_keys]
    labels = [m.strftime("%b %Y") for m in month_keys]

    sb_count = grp.size().tolist()
    charge   = grp["charge_amount_clean"].sum().round(2).tolist()

    statuses = ["Paid", "Denied", "Pending", "Submitted",
                "Resubmitted", "Rejected", "Not Submitted", "Unknown"]
    status_breakdown = {}
    for st in statuses:
        series = (
            d.assign(_f=d["claim_status_normalized"].eq(st).astype(int))
             .groupby("_m")["_f"].sum()
             .reindex(month_keys, fill_value=0)
        )
        status_breakdown[st] = [int(v) for v in series.tolist()]

    sub   = grp["is_submitted"].sum()
    paid  = grp["is_paid"].sum()
    den   = grp["is_denied"].sum()
    total = grp.size()

    submission_rate = (100 * sub / total).round(2).fillna(0).tolist()
    paid_rate   = (100 * (paid / sub)).replace([np.inf, -np.inf], 0).round(2).fillna(0).tolist()
    denial_rate = (100 * (den / sub)).replace([np.inf, -np.inf], 0).round(2).fillna(0).tolist()

    return {
        "months": months,
        "labels": labels,
        "sb_count": [int(v) for v in sb_count],
        "charge_amount": [float(v) for v in charge],
        "status_breakdown": status_breakdown,
        "submission_rate": [float(v) for v in submission_rate],
        "paid_rate":       [float(v) for v in paid_rate],
        "denial_rate":     [float(v) for v in denial_rate],
    }


def status_breakdown(df: pd.DataFrame) -> dict:
    counts = df["claim_status_normalized"].value_counts(dropna=False).to_dict()
    labels, values = [], []
    for k, v in counts.items():
        labels.append(str(k) if k is not None else "Unknown")
        values.append(int(v))
    return {"labels": labels, "values": values}


def aging_breakdown(df: pd.DataFrame) -> dict:
    labels = [b[0] for b in config.AGING_BUCKETS]
    outstanding = df[df["is_outstanding"]]
    counts, charges = [], []
    for label in labels:
        sub = outstanding[outstanding["aging_bucket"] == label]
        counts.append(int(len(sub)))
        charges.append(round(float(sub["charge_amount_clean"].sum(skipna=True)), 2))
    return {"labels": labels, "counts": counts, "charges": charges}


def calculate_payer_metrics(df: pd.DataFrame) -> dict:
    rows = []
    for payer, g in df.groupby("payer_display", dropna=False):
        sub  = int(g["is_submitted"].sum())
        paid = int(g["is_paid"].sum())
        den  = int(g["is_denied"].sum())
        rows.append({
            "payer": payer if payer else "Unknown",
            "superbill_count": int(len(g)),
            "submitted": sub,
            "paid": paid,
            "denied": den,
            "pending": int(g["is_pending"].sum()),
            "submission_rate":    round(100 * _safe_div(sub,  len(g)), 2),
            "paid_rate":          round(100 * _safe_div(paid, sub),    2),
            "denial_rate":        round(100 * _safe_div(den,  sub),    2),
            "charge_amount":      round(float(g["charge_amount_clean"].sum(skipna=True)), 2),
            "outstanding_charge": round(float(g.loc[g["is_outstanding"], "charge_amount_clean"].sum(skipna=True)), 2),
        })
    rows.sort(key=lambda r: r["charge_amount"], reverse=True)

    top = rows[:10]
    top_payers_chart = {
        "labels": [r["payer"] for r in top],
        "values": [r["charge_amount"] for r in top],
    }
    ranked = [r for r in rows if r["submitted"] >= config.MIN_SUBMITTED_FOR_RATE_RANKING]
    ranked.sort(key=lambda r: r["denial_rate"], reverse=True)
    denial_chart = {
        "labels": [r["payer"] for r in ranked[:10]],
        "values": [r["denial_rate"] for r in ranked[:10]],
    }
    return {"table": rows, "top_payers": top_payers_chart, "denial_by_payer": denial_chart}


def calculate_provider_metrics(df: pd.DataFrame) -> list:
    rows = []
    for provider, g in df.groupby("provider_display", dropna=False):
        sub  = int(g["is_submitted"].sum())
        paid = int(g["is_paid"].sum())
        den  = int(g["is_denied"].sum())
        rows.append({
            "provider": provider if provider else "Unknown",
            "total_superbills":   int(len(g)),
            "total_charge":       round(float(g["charge_amount_clean"].sum(skipna=True)), 2),
            "submitted":          sub,
            "submission_rate":    round(100 * _safe_div(sub,  len(g)), 2),
            "paid":               paid,
            "paid_rate":          round(100 * _safe_div(paid, sub),    2),
            "denied":             den,
            "denial_rate":        round(100 * _safe_div(den,  sub),    2),
            "pending":            int(g["is_pending"].sum()),
            "outstanding_claims": int(g["is_outstanding"].sum()),
            "outstanding_charge": round(float(g.loc[g["is_outstanding"], "charge_amount_clean"].sum(skipna=True)), 2),
        })
    rows.sort(key=lambda r: r["total_charge"], reverse=True)
    return rows


def calculate_data_quality(df: pd.DataFrame, orphan: pd.DataFrame, dup_info: dict) -> dict:
    return {
        "missing_from_tracker":            int((~df["in_tracker"]).sum()),
        "tracker_rows_without_superbill":  int(len(orphan)),
        "duplicate_superbill_ids_in_sb":   int(dup_info["superbill_dupes"].shape[0]),
        "duplicate_superbill_ids_in_tr":   int(dup_info["tracker_dupes"].shape[0]),
        "submitted_without_claim_number":  int(df["submitted_without_claim_number"].sum()),
        "missing_status":                  int(df["missing_status"].sum()),
        "missing_claim_number":            int((df["in_tracker"] & df["missing_claim_number"]).sum()),
        "missing_provider":                int(df["missing_provider"].sum()),
        "missing_payer":                   int(df["missing_payer"].sum()),
        "missing_charge_amount":           int(df["missing_charge_amount"].sum()),
        "duplicate_superbill_list_sb":     dup_info["superbill_dupes"].to_dict(orient="records"),
        "duplicate_superbill_list_tr":     dup_info["tracker_dupes"].to_dict(orient="records"),
    }


def generate_executive_summary(df: pd.DataFrame, kpis: dict, monthly: dict,
                               payer: dict, dq: dict) -> List[str]:
    out = []
    total_items = kpis["total_billable_items"]
    if total_items == 0:
        return ["No SuperBills in the current view."]

    out.append(
        f"{kpis['total_superbills']:,} distinct SuperBills (by NPI × SB ID) across "
        f"{total_items:,} billable items. "
        f"{kpis['submission_rate']:.1f}% submitted "
        f"({kpis['total_submitted']:,} submitted, {kpis['yet_to_submit_count']:,} yet to submit)."
    )
    if kpis["total_submitted"] > 0:
        out.append(
            f"Paid rate is {kpis['paid_rate']:.1f}% and denial rate is "
            f"{kpis['denial_rate']:.1f}% of submitted claims."
        )

    if kpis["outstanding_sub_charges"] > 0 or kpis["yet_to_submit_charges"] > 0:
        out.append(
            f"${kpis['outstanding_pending_charges']:,.2f} with payer (pending), "
            f"${kpis['outstanding_rework_charges']:,.2f} needs rework, "
            f"${kpis['yet_to_submit_charges']:,.2f} still to submit."
        )
    if kpis.get("oldest_outstanding_days", 0) >= 60:
        out.append(
            f"Oldest outstanding submitted claim is {kpis['oldest_outstanding_days']} days old "
            f"since SuperBill generation."
        )

    aged = df[df["is_outstanding"] & df["days_since_generated"].fillna(0).ge(91)]
    if len(aged) > 0:
        out.append(
            f"{len(aged):,} outstanding claims have aged beyond 90 days since SuperBill generation."
        )

    if monthly["labels"] and len(monthly["labels"]) >= 2:
        prev, curr = monthly["denial_rate"][-2], monthly["denial_rate"][-1]
        prev_lbl, curr_lbl = monthly["labels"][-2], monthly["labels"][-1]
        if prev > 0 or curr > 0:
            delta = curr - prev
            direction = "increased" if delta > 0 else "decreased" if delta < 0 else "held steady"
            out.append(
                f"Denial rate {direction} from {prev:.1f}% in {prev_lbl} to {curr:.1f}% in {curr_lbl}."
            )

    ranked = [r for r in payer["table"]
              if r["submitted"] >= config.MIN_SUBMITTED_FOR_RATE_RANKING]
    if ranked:
        worst = max(ranked, key=lambda r: r["denial_rate"])
        if worst["denial_rate"] > 0:
            out.append(
                f"{worst['payer']} has the highest denial rate "
                f"({worst['denial_rate']:.1f}%) among payers with at least "
                f"{config.MIN_SUBMITTED_FOR_RATE_RANKING} submitted claims."
            )

    if dq["missing_from_tracker"] > 0:
        out.append(
            f"{dq['missing_from_tracker']:,} SuperBills are not represented "
            f"in the Revenue Tracker (treated as Not Submitted)."
        )

    if dq["submitted_without_claim_number"] > 0:
        out.append(
            f"{dq['submitted_without_claim_number']:,} submitted claims are missing a Claim #."
        )

    return out


_DETAIL_COLS = [
    ("superbill_id_clean",         "SuperBill ID"),
    ("Billing Month Name",         "Billing Month"),
    ("provider_display",           "Provider"),
    ("GGH Member ID",              "GGH Member ID"),
    ("Member Name",                "Member Name"),
    ("payer_display",              "Payer"),
    ("Service From Date",          "Service From"),
    ("Service Through Date",       "Service Through"),
    ("Procedure Code",             "Procedure"),
    ("Units",                      "Units"),
    ("Total Qualifying Minutes",   "Qualifying Min"),
    ("charge_amount_clean",        "Charge Amount"),
    ("Superbill Generated Date",   "Generated"),
    ("Superbill Status",           "SB Status"),
    ("Claims Submitted",           "Submitted?"),
    ("Claim #",                    "Claim #"),
    ("Claim Status",               "Original Status"),
    ("claim_status_normalized",    "Normalized Status"),
    ("Denial Reason",              "Denial Reason"),
    ("is_resubmitted",             "Resubmitted"),
    ("days_since_generated",       "Aging Days"),
    ("aging_bucket",               "Aging Bucket"),
]


def detail_rows(df: pd.DataFrame) -> dict:
    cols_present = [(k, h) for (k, h) in _DETAIL_COLS if k in df.columns]
    headers = [h for _, h in cols_present]
    keys    = [k for k, _ in cols_present]

    rows = []
    for _, r in df.iterrows():
        row = []
        for k in keys:
            v = r[k]
            if pd.isna(v):
                row.append("")
            elif isinstance(v, (pd.Timestamp, datetime)):
                row.append(pd.Timestamp(v).strftime("%Y-%m-%d"))
            elif isinstance(v, bool):
                row.append("Yes" if v else "No")
            elif isinstance(v, float):
                row.append(round(v, 2))
            else:
                row.append(str(v))
        rows.append(row)

    return {"headers": headers, "rows": rows}


def detail_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Streamlit-friendly: return a DataFrame of the detail rows (not row-of-lists)."""
    detail = detail_rows(df)
    return pd.DataFrame(detail["rows"], columns=detail["headers"])