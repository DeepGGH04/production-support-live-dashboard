# GGH Revenue Cycle Dashboard — Streamlit

Streamlit port of the Flask + Plotly.js revenue cycle dashboard. Reads
the SuperBill and Revenue Tracker Excel files from **Azure Blob
Storage** (manual refresh model) and shows claim-lifecycle KPIs,
monthly trends, status/aging breakdowns, payer and provider
performance, data quality, and a filtered claim-detail table with CSV
export.

All business rules — the `(SuperBill ID, HCID)` LEFT JOIN, the "not in
tracker → Not Submitted" rule, the Claim-Status map, the aging buckets,
the NPI-only provider display, the outstanding-charge definition — are
identical to the Flask version.

---

## Deploying to Streamlit Community Cloud

This repo replaces the existing app at
`https://ggh-support-live-dashboard.streamlit.app/`.

### 1. Set up Azure Blob Storage (one-time)

1. In the Azure Portal, create a Storage Account (or reuse an existing
   one). Standard LRS is fine.
2. Create a **private** blob container, e.g. `revenue-cycle`.
3. Upload the two Excel files under fixed names (e.g.
   `SuperBill_latest.xlsx`, `SuperBill_tracker_latest.xlsx`). The
   dashboard always reads from these fixed names so you can replace
   files in place.
4. In the Storage Account → Security + networking → Access keys, copy
   the full **Connection string**.

### 2. Push this folder to the git repo backing the Streamlit app

Replace the current repo contents with the files in this folder:

```
streamlit_app.py
config.py
data_loader.py
data_processor.py
metrics.py
charts.py
requirements.txt
.gitignore
.streamlit/config.toml
.streamlit/secrets.toml.example   ← keep for reference
README.md
```

Delete the old Flask files from the repo:
`app.py`, `templates/`, `static/`. The old `config.py`, `data_loader.py`,
`data_processor.py`, `metrics.py`, `requirements.txt`, `.gitignore`,
`README.md` all get replaced.

### 3. Point Streamlit Cloud at the new entry point

In the Streamlit Cloud app settings for `ggh-support-live-dashboard`:

- **Main file path:** `streamlit_app.py`
- **Python version:** 3.11 or later
- **Secrets:** paste the contents of your real `secrets.toml` (see
  `.streamlit/secrets.toml.example` for the shape) into the Secrets box.
  Do NOT commit the real `secrets.toml`.

Click **Reboot app**. Streamlit will pull the new commit, install
`requirements.txt`, and launch `streamlit_app.py`.

### 4. Refreshing data

Whenever SuperBill or Revenue Tracker is updated:

1. Upload the new file to the blob container under the same name
   (overwrite the existing blob).
2. In the dashboard, click **🔄 Refresh Data** at the top of the page.
   This clears the Streamlit cache and re-pulls both blobs.

---

## Running locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
# edit .streamlit\secrets.toml with your real connection string
streamlit run streamlit_app.py
```

The app opens at <http://localhost:8501>.

---

## File map

| File                | Purpose                                                        |
|---------------------|----------------------------------------------------------------|
| `streamlit_app.py`  | Streamlit UI — sidebar filters, KPI cards, charts, detail tab. |
| `config.py`         | Status map, aging buckets, required columns, thresholds.       |
| `data_loader.py`    | Pulls SuperBill + Tracker blobs from Azure Blob Storage.       |
| `data_processor.py` | Clean, normalize, LEFT JOIN, derive fields.                    |
| `metrics.py`        | KPIs, monthly, aging, payer/provider, data quality, summary.   |
| `charts.py`         | Plotly figure builders used by the Streamlit tabs.             |
| `.streamlit/`       | `config.toml` (theme), `secrets.toml.example`.                 |

---

## Privacy

- The Azure connection string lives only in Streamlit Cloud secrets —
  it is NOT in the repo.
- `.gitignore` blocks `*.xlsx`, `*.xls`, `*.csv`, `.env`, and
  `.streamlit/secrets.toml`.
- The blob container should remain private; the app authenticates with
  the account key from secrets. No public blob access is required.
- Streamlit Community Cloud apps are public URLs by default. Use the
  Streamlit Cloud **"Viewer authentication"** (SSO) option to restrict
  access to GGH emails.

---

## Known limitations (unchanged from Flask version)

1. **Charge Amount is NOT collected revenue.** The source data has no
   payment amount.
2. **Aging is time-since-generation**, not true Days-in-AR.
3. **Resubmission is boolean** — we can detect that a claim was
   resubmitted but not how many times or against which original.
4. **Manual tracker lag.** Recently-generated SuperBills that haven't
   been typed into the tracker show as *Not Submitted* until they are.
5. **Status normalization is a map.** New raw status strings not in
   `config.CLAIM_STATUS_MAP` show as `Unknown` until added.
