"""
Clean, normalize, and merge SuperBill + Revenue Tracker.
Produces the unified df_claims used by metrics.py.

Join rule: LEFT JOIN SuperBill -> Tracker on (SuperBill ID, HCID).
Overlapping columns are dropped from the tracker side before merging;
SuperBill is treated as the authoritative source for everything it carries.
"""
import re
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

import config


# -----------------------------------------------------------------------------
# Low-level normalizers
# -----------------------------------------------------------------------------
def _norm_str(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    s = str(v).strip()
    if s == "" or s.lower() in {"nan", "none", "null", "n/a", "na", "#n/a"}:
        return None
    return s


def _norm_id(v):
    s = _norm_str(v)
    if s is None:
        return None
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return s.upper()


def _norm_hcid(v):
    s = _norm_str(v)
    if s is None:
        return None
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except (ValueError, TypeError):
        pass
    return s.upper().replace(" ", "")


def normalize_yes_no(v):
    s = _norm_str(v)
    if s is None:
        return "Unknown"
    low = s.lower()
    if low in config.YES_VALUES:
        return True
    if low in config.NO_VALUES:
        return False
    return "Unknown"


def normalize_claim_status(v):
    s = _norm_str(v)
    if s is None:
        return "Unknown"
    key = s.lower().strip()
    return config.CLAIM_STATUS_MAP.get(key, "Unknown")


def _norm_money(v):
    if v is None:
        return (np.nan, True)
    if isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)):
        return (float(v), False)
    s = _norm_str(v)
    if s is None:
        return (np.nan, True)
    cleaned = re.sub(r"[^\d\.\-]", "", s)
    if cleaned in {"", "-", ".", "-."}:
        return (np.nan, True)
    try:
        return (float(cleaned), False)
    except ValueError:
        return (np.nan, True)


def _norm_date(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return pd.NaT
    try:
        return pd.to_datetime(v, errors="coerce")
    except Exception:
        return pd.NaT


def _parse_billing_month(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return (None, None)
    if isinstance(v, (pd.Timestamp, datetime)):
        try:
            return (int(v.month), int(v.year))
        except Exception:
            return (None, None)
    s = _norm_str(v)
    if s is None:
        return (None, None)
    s_norm = s.replace(".", " ").replace("_", " ")
    for fmt in (
        "%B %Y", "%b %Y", "%Y-%m", "%m/%Y", "%m-%Y", "%Y/%m",
        "%B-%Y", "%b-%Y", "%Y %B", "%Y %b", "%Y-%B", "%Y-%b",
        "%b %y", "%B %y", "%b'%y", "%B'%y", "%b %Y %d", "%B %Y %d",
    ):
        try:
            d = datetime.strptime(s_norm, fmt)
            return (d.month, d.year)
        except ValueError:
            continue
    for fmt in ("%B", "%b"):
        try:
            d = datetime.strptime(s_norm, fmt)
            return (d.month, None)
        except ValueError:
            continue
    try:
        d = pd.to_datetime(s, errors="coerce")
        if pd.notna(d):
            return (int(d.month), int(d.year))
    except Exception:
        pass
    return (None, None)


# -----------------------------------------------------------------------------
# Table-level cleaning
# -----------------------------------------------------------------------------
_DATE_COLS = [
    "Service From Date", "Service Through Date",
    "Date Of Birth", "Superbill Generated Date",
]


def clean_superbill(df: pd.DataFrame, year_hint: Optional[int] = None) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(_norm_str)

    df["superbill_id_clean"] = df["SuperBill ID"].map(_norm_id)
    df["hcid_clean"] = df.get(
        "Payer Member ID / HCID", pd.Series([None] * len(df))
    ).map(_norm_hcid)

    for c in _DATE_COLS:
        if c in df.columns:
            df[c] = df[c].map(_norm_date)

    parsed = df["Billing Month Name"].map(_parse_billing_month)
    def _col(name):
        return df[name] if name in df.columns else pd.Series([pd.NaT] * len(df))
    gen         = _col("Superbill Generated Date")
    svc_from    = _col("Service From Date")
    svc_through = _col("Service Through Date")

    hint = year_hint or datetime.now().year

    def _resolve(mo_yr, g, sf, st_):
        m, y = mo_yr
        if m is None:
            return pd.NaT
        if y is None:
            for d in (g, sf, st_):
                if pd.notna(d):
                    y = pd.Timestamp(d).year
                    break
            else:
                y = hint
        try:
            return pd.Timestamp(datetime(y, m, 1))
        except Exception:
            return pd.NaT

    df["billing_month_key"] = [
        _resolve(my, g, sf, st_)
        for my, g, sf, st_ in zip(parsed, gen, svc_from, svc_through)
    ]

    money = df["Charge Amount"].map(_norm_money)
    df["charge_amount_clean"] = money.map(lambda t: t[0])
    df["charge_amount_was_missing"] = money.map(lambda t: t[1])

    return df


def clean_tracker(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(_norm_str)

    df["superbill_id_clean"] = df["SuperBill ID"].map(_norm_id)
    df["hcid_clean"] = df.get(
        "Payer Member ID / HCID", pd.Series([None] * len(df))
    ).map(_norm_hcid)

    for c in ["Sent to Provider", "Received by Provider", "Claims Submitted"]:
        if c in df.columns:
            df[c + "_norm"] = df[c].map(normalize_yes_no)

    df["claim_status_normalized"] = df.get(
        "Claim Status", pd.Series([None] * len(df))
    ).map(normalize_claim_status)

    return df


# -----------------------------------------------------------------------------
# Resubmission detection
# -----------------------------------------------------------------------------
def _contains_resubmit_token(*values) -> bool:
    for v in values:
        s = _norm_str(v)
        if not s:
            continue
        low = s.lower()
        for tok in config.RESUBMIT_TOKENS:
            if tok in low:
                return True
    return False


# -----------------------------------------------------------------------------
# Merge
# -----------------------------------------------------------------------------
_TRACKER_KEEP_COLS = [
    "superbill_id_clean",
    "hcid_clean",
    "Super Bill File Name",
    "Provider",
    "Group Type",
    "Contracting/Billing Entity",
    "Payer ID",
    "Payer From Availity",
    "Plan Name from Availity",
    "Units",
    "Sent to Provider",
    "Received by Provider",
    "Claims Submitted",
    "Reason",
    "Claim #",
    "Claim Status",
    "Denial Reason",
    "Sent to Provider_norm",
    "Received by Provider_norm",
    "Claims Submitted_norm",
    "claim_status_normalized",
]


def _composite_dup_report(df: pd.DataFrame) -> pd.DataFrame:
    if "superbill_id_clean" not in df.columns or "hcid_clean" not in df.columns:
        return pd.DataFrame(columns=["superbill_id_clean", "hcid_clean", "count"])
    counts = (
        df.groupby(["superbill_id_clean", "hcid_clean"], dropna=False)
          .size().reset_index(name="count")
    )
    return counts[counts["count"] > 1]


def match_superbill_tracker(sb: pd.DataFrame, tr: pd.DataFrame):
    sb_dups = _composite_dup_report(sb)
    tr_dups = _composite_dup_report(tr)

    keep = [c for c in _TRACKER_KEEP_COLS if c in tr.columns]
    tr_slim = tr[keep].copy()

    merged = sb.merge(
        tr_slim,
        how="left",
        on=["superbill_id_clean", "hcid_clean"],
        indicator=True,
    )
    merged["in_tracker"] = merged["_merge"] == "both"
    merged = merged.drop(columns=["_merge"])

    sb_pairs = set(zip(sb["superbill_id_clean"], sb["hcid_clean"]))
    tr_pairs = list(zip(tr["superbill_id_clean"], tr["hcid_clean"]))
    orphan_mask = pd.Series(
        [p not in sb_pairs or p[0] is None or p[1] is None for p in tr_pairs],
        index=tr.index,
    )
    df_orphan = tr.loc[orphan_mask].copy()

    dup_info = {"superbill_dupes": sb_dups, "tracker_dupes": tr_dups}
    return merged, df_orphan, dup_info


# -----------------------------------------------------------------------------
# Derived fields
# -----------------------------------------------------------------------------
def calculate_aging(generated_date, today=None):
    if pd.isna(generated_date):
        return np.nan
    today = today or pd.Timestamp(datetime.now().date())
    return int((today - pd.Timestamp(generated_date).normalize()).days)


def _aging_bucket(days) -> str:
    if pd.isna(days):
        return "Unknown"
    for label, lo, hi in config.AGING_BUCKETS:
        if lo <= days <= hi:
            return label
    return "Unknown"


def derive_fields(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "claim_status_normalized" not in df.columns:
        df["claim_status_normalized"] = "Unknown"
    df["claim_status_normalized"] = df["claim_status_normalized"].fillna("Unknown")

    not_in_tracker = ~df["in_tracker"]
    df.loc[not_in_tracker, "claim_status_normalized"] = "Not Submitted"

    s = df["claim_status_normalized"]
    df["is_paid"]                 = s.eq("Paid")
    df["is_denied"]               = s.eq("Denied")
    df["is_pending"]              = s.eq("Pending")
    df["is_rejected"]             = s.eq("Rejected")
    df["is_not_submitted"]        = s.eq("Not Submitted")
    df["is_declined_at_provider"] = s.eq("Declined at Provider")

    sub_col = "Claims Submitted_norm"
    if sub_col not in df.columns:
        df[sub_col] = "Unknown"
    df[sub_col] = df[sub_col].where(df["in_tracker"], False)

    df["is_submitted"] = s.isin(
        ["Paid", "Denied", "Pending", "Resubmitted", "Rejected"]
    )

    df["is_sent_to_provider"]     = df.get("Sent to Provider_norm", "Unknown")
    df["is_received_by_provider"] = df.get("Received by Provider_norm", "Unknown")

    reason     = df.get("Reason",        pd.Series([None] * len(df)))
    denial     = df.get("Denial Reason", pd.Series([None] * len(df)))
    status_raw = df.get("Claim Status",  pd.Series([None] * len(df)))
    df["is_resubmitted"] = [
        s_norm == "Resubmitted" or _contains_resubmit_token(sr, rz, dz)
        for s_norm, sr, rz, dz in zip(
            df["claim_status_normalized"], status_raw, reason, denial
        )
    ]

    def _payer(row):
        for col in ["Plan Name from Availity", "Payer From Availity", "Payer ID"]:
            v = row.get(col)
            s_ = _norm_str(v)
            if s_:
                return s_
        return "Unknown"
    df["payer_display"] = df.apply(_payer, axis=1)

    def _provider(row):
        for col in ["Provider", "Billing Provider NPI", "Rendering Provider NPI"]:
            v = row.get(col)
            s_ = _norm_str(v)
            if s_:
                return s_
        return "Unknown"
    df["provider_display"] = df.apply(_provider, axis=1)

    today = pd.Timestamp(datetime.now().date())
    df["days_since_generated"] = df["Superbill Generated Date"].map(
        lambda d: calculate_aging(d, today)
    )
    if "Service Through Date" in df.columns:
        df["days_since_service_through"] = df["Service Through Date"].map(
            lambda d: calculate_aging(d, today)
        )
    df["aging_bucket"] = df["days_since_generated"].map(_aging_bucket)

    df["is_outstanding"] = df["is_submitted"] & ~df["is_paid"] & ~df["is_rejected"]

    df["missing_claim_number"] = df.get("Claim #", pd.Series([None] * len(df))).map(
        lambda v: _norm_str(v) is None
    )
    df["submitted_without_claim_number"] = df["is_submitted"] & df["missing_claim_number"]
    df["missing_provider"]      = df["provider_display"].eq("Unknown")
    df["missing_payer"]         = df["payer_display"].eq("Unknown")
    df["missing_charge_amount"] = df["charge_amount_clean"].isna()
    df["missing_status"]        = df["claim_status_normalized"].eq("Unknown") & df["in_tracker"]

    return df


def build_claims_dataframe(sb_raw: pd.DataFrame, tr_raw: pd.DataFrame,
                           year_hint: Optional[int] = None):
    sb = clean_superbill(sb_raw, year_hint=year_hint)
    tr = clean_tracker(tr_raw)
    merged, orphan, dup_info = match_superbill_tracker(sb, tr)
    df_claims = derive_fields(merged)
    return df_claims, orphan, dup_info
