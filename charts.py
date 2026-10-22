"""
Plotly figure builders for the Streamlit dashboard.
Each function takes the pre-computed metrics dict and returns a Figure.
"""
import plotly.graph_objects as go


# Brand-neutral palette tuned for light + dark Streamlit themes.
PALETTE = {
    "Paid":                 "#2E7D32",
    "Denied":               "#C62828",
    "Pending":              "#1565C0",
    "Submitted":            "#1565C0",
    "Resubmitted":          "#6A1B9A",
    "Rejected":             "#EF6C00",
    "Not Submitted":        "#616161",
    "Declined at Provider": "#8D6E63",
    "Unknown":              "#9E9E9E",
}

PRIMARY = "#1565C0"
ACCENT = "#2E7D32"
WARN = "#C62828"


def _common_layout(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=30, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


def monthly_volume(monthly: dict) -> go.Figure:
    fig = go.Figure()
    if not monthly["labels"]:
        return _common_layout(fig)
    fig.add_bar(
        x=monthly["labels"],
        y=monthly["sb_count"],
        name="SuperBills",
        marker_color=PRIMARY,
    )
    fig.add_scatter(
        x=monthly["labels"],
        y=monthly["charge_amount"],
        name="Charge Amount ($)",
        yaxis="y2",
        mode="lines+markers",
        line=dict(color=ACCENT, width=2),
    )
    fig.update_layout(
        title="Monthly SuperBill Volume and Charges",
        yaxis=dict(title="SuperBills"),
        yaxis2=dict(title="Charges ($)", overlaying="y", side="right",
                    showgrid=False, tickformat=","),
    )
    return _common_layout(fig)


def monthly_rates(monthly: dict) -> go.Figure:
    fig = go.Figure()
    if not monthly["labels"]:
        return _common_layout(fig)
    fig.add_scatter(x=monthly["labels"], y=monthly["submission_rate"],
                    mode="lines+markers", name="Submission %",
                    line=dict(color=PRIMARY, width=2))
    fig.add_scatter(x=monthly["labels"], y=monthly["paid_rate"],
                    mode="lines+markers", name="Paid % (of submitted)",
                    line=dict(color=ACCENT, width=2))
    fig.add_scatter(x=monthly["labels"], y=monthly["denial_rate"],
                    mode="lines+markers", name="Denial % (of submitted)",
                    line=dict(color=WARN, width=2))
    fig.update_layout(
        title="Monthly Submission, Paid, and Denial Rates",
        yaxis=dict(title="%", ticksuffix="%"),
    )
    return _common_layout(fig)


def status_donut(status: dict) -> go.Figure:
    colors = [PALETTE.get(label, "#9E9E9E") for label in status["labels"]]
    fig = go.Figure(go.Pie(
        labels=status["labels"],
        values=status["values"],
        hole=0.55,
        marker=dict(colors=colors),
        textinfo="percent",
    ))
    fig.update_layout(title="Claim Status Breakdown")
    return _common_layout(fig)


def aging_bars(aging: dict) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        x=aging["labels"], y=aging["counts"],
        name="Outstanding Claims", marker_color=PRIMARY,
    )
    fig.add_scatter(
        x=aging["labels"], y=aging["charges"], name="Outstanding Charges ($)",
        yaxis="y2", mode="lines+markers", line=dict(color=WARN, width=2),
    )
    fig.update_layout(
        title="Aging of Outstanding Claims (days since Superbill Generated)",
        yaxis=dict(title="Claims"),
        yaxis2=dict(title="Charges ($)", overlaying="y", side="right",
                    showgrid=False, tickformat=","),
    )
    return _common_layout(fig)


def top_payers_bar(top: dict) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=top["values"], y=top["labels"],
        orientation="h", marker_color=PRIMARY,
    ))
    fig.update_layout(
        title="Top 10 Payers by Charge Amount",
        xaxis=dict(title="Charges ($)", tickformat=","),
        yaxis=dict(autorange="reversed"),
    )
    return _common_layout(fig, height=420)


def denial_by_payer_bar(denial: dict) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=denial["values"], y=denial["labels"],
        orientation="h", marker_color=WARN,
    ))
    fig.update_layout(
        title="Highest Denial Rate by Payer (min submitted claims)",
        xaxis=dict(title="Denial Rate", ticksuffix="%"),
        yaxis=dict(autorange="reversed"),
    )
    return _common_layout(fig, height=420)
