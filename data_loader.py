"""
Load SuperBill and Revenue Tracker Excel files from Azure Blob Storage.
Validate required columns. Return (dataframe, file_info) tuples.

Azure settings come from Streamlit secrets (st.secrets["azure"]):
    connection_string   full Azure Storage connection string
    container           blob container name
    superbill_blob      blob name of the SuperBill Excel file
    tracker_blob        blob name of the Revenue Tracker Excel file
    superbill_sheet     optional, defaults to the first sheet
    tracker_sheet       optional, defaults to the first sheet
"""
import io
import re
from datetime import datetime, timezone
from typing import Tuple, Dict, List, Optional

import pandas as pd
import streamlit as st
from azure.storage.blob import BlobServiceClient

import config


def _azure_cfg() -> dict:
    try:
        return dict(st.secrets["azure"])
    except Exception as e:
        raise RuntimeError(
            "Azure settings missing from Streamlit secrets. Add an [azure] "
            "section with connection_string, container, superbill_blob, and "
            "tracker_blob."
        ) from e


def _get_blob_client(blob_name: str):
    cfg = _azure_cfg()
    svc = BlobServiceClient.from_connection_string(cfg["connection_string"])
    return svc.get_blob_client(container=cfg["container"], blob=blob_name)


def _blob_info(blob_name: str, label: str) -> Dict:
    """Return filename, modified timestamp, and size for a blob."""
    try:
        client = _get_blob_client(blob_name)
        props = client.get_blob_properties()
        modified = props.last_modified
        if modified and modified.tzinfo is None:
            modified = modified.replace(tzinfo=timezone.utc)
        return {
            "path": f"azure://{client.container_name}/{blob_name}",
            "filename": blob_name,
            "exists": True,
            "modified": modified.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                        if modified else None,
            "size_bytes": int(props.size or 0),
            "rows": 0,
            "error": None,
        }
    except Exception as e:
        return {
            "path": f"azure://.../{blob_name}",
            "filename": blob_name,
            "exists": False,
            "modified": None,
            "size_bytes": 0,
            "rows": 0,
            "error": f"{label} blob not readable: {e}",
        }


def _download_blob_bytes(blob_name: str) -> bytes:
    client = _get_blob_client(blob_name)
    stream = client.download_blob()
    return stream.readall()


def _validate_columns(df: pd.DataFrame, required: List[str], label: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{label} is missing required column(s): {', '.join(missing)}"
        )


def _read_excel_from_bytes(data: bytes, sheet) -> pd.DataFrame:
    return pd.read_excel(
        io.BytesIO(data),
        sheet_name=sheet if sheet else 0,
        engine="openpyxl",
        dtype=object,
    )


def load_superbill() -> Tuple[pd.DataFrame, Dict]:
    cfg = _azure_cfg()
    blob_name = cfg["superbill_blob"]
    info = _blob_info(blob_name, "SuperBill")
    if not info["exists"]:
        raise FileNotFoundError(info["error"])
    raw = _download_blob_bytes(blob_name)
    df = _read_excel_from_bytes(raw, cfg.get("superbill_sheet"))
    df.columns = [str(c).strip() for c in df.columns]
    _validate_columns(df, config.REQUIRED_SUPERBILL_COLUMNS, "SuperBill")
    info["rows"] = len(df)
    return df, info


def load_tracker() -> Tuple[pd.DataFrame, Dict]:
    cfg = _azure_cfg()
    blob_name = cfg["tracker_blob"]
    info = _blob_info(blob_name, "Revenue Tracker")
    if not info["exists"]:
        raise FileNotFoundError(info["error"])
    raw = _download_blob_bytes(blob_name)
    df = _read_excel_from_bytes(raw, cfg.get("tracker_sheet"))
    df.columns = [str(c).strip() for c in df.columns]
    _validate_columns(df, config.REQUIRED_TRACKER_COLUMNS, "Revenue Tracker")
    info["rows"] = len(df)
    return df, info


def year_hint_from_superbill_blob() -> Optional[int]:
    """Extract a 4-digit year (2000-2099) from the SuperBill blob name."""
    try:
        cfg = _azure_cfg()
        m = re.search(r"(20\d{2})", str(cfg.get("superbill_blob", "")))
        return int(m.group(1)) if m else None
    except Exception:
        return None
