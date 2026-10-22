"""
Configuration for the Revenue Cycle Dashboard (Streamlit edition).

File paths are no longer here — SuperBill and Revenue Tracker come from
Azure Blob Storage, configured via Streamlit secrets (see
.streamlit/secrets.toml.example). Everything else — status normalization,
aging buckets, required columns, thresholds — is unchanged from the
Flask version.
"""

# -----------------------------------------------------------------------------
# Rate-ranking volume threshold.
# A payer/provider must have at least this many submitted claims before it is
# ranked by denial/paid rate. Prevents 1-of-1 outliers from topping the list.
# -----------------------------------------------------------------------------
MIN_SUBMITTED_FOR_RATE_RANKING = 10

# -----------------------------------------------------------------------------
# Aging buckets, in days since Superbill Generated Date.
# -----------------------------------------------------------------------------
AGING_BUCKETS = [
    ("0-30",   0,   30),
    ("31-60",  31,  60),
    ("61-90",  61,  90),
    ("91-120", 91,  120),
    ("120+",   121, 10_000),
]

# -----------------------------------------------------------------------------
# Required columns. Loading fails cleanly if any are missing.
# -----------------------------------------------------------------------------
REQUIRED_SUPERBILL_COLUMNS = [
    "SuperBill ID",
    "Payer Member ID / HCID",
    "Billing Month Name",
    "Charge Amount",
    "Superbill Generated Date",
]

REQUIRED_TRACKER_COLUMNS = [
    "SuperBill ID",
    "Payer Member ID / HCID",
    "Provider",
    "Claims Submitted",
    "Claim Status",
]

# -----------------------------------------------------------------------------
# Claim Status normalization map.
# -----------------------------------------------------------------------------
CLAIM_STATUS_MAP = {
    # Paid
    "paid": "Paid",
    "payment received": "Paid",
    "pd": "Paid",
    "paid in full": "Paid",
    "closed - paid": "Paid",
    "closed paid": "Paid",

    # Denied
    "denied": "Denied",
    "denial": "Denied",
    "denied - resubmit": "Denied",
    "denied-resubmit": "Denied",
    "denied/resubmit": "Denied",
    "denied/resubmitted": "Denied",

    # Pending
    "submitted": "Pending",
    "accepted": "Pending",
    "acknowledged": "Pending",
    "pending": "Pending",
    "sent": "Pending",
    "filed": "Pending",
    "in process": "Pending",
    "in progress": "Pending",
    "in review": "Pending",
    "under review": "Pending",
    "processing": "Pending",
    "open": "Pending",

    # Resubmitted
    "resubmitted": "Resubmitted",
    "refiled": "Resubmitted",
    "re-filed": "Resubmitted",
    "corrected claim submitted": "Resubmitted",
    "corrected claim": "Resubmitted",

    # Rejected
    "rejected": "Rejected",
    "277ca reject": "Rejected",
    "front-end reject": "Rejected",
    "front end reject": "Rejected",

    # Declined at Provider
    "declined at provider": "Declined at Provider",
    "declined by provider": "Declined at Provider",
    "provider declined": "Declined at Provider",
}

YES_VALUES = {"yes", "y", "true", "1", "t", "x"}
NO_VALUES  = {"no", "n", "false", "0", "f"}

RESUBMIT_TOKENS = ["resubmit", "refiled", "re-filed", "corrected", "appeal filed"]
