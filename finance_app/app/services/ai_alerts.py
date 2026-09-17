"""
services/ai_alerts.py — Smart Overspending Alert Engine
────────────────────────────────────────────────────────
Six intelligent alert types powered by user's SQLAlchemy transaction data:

  BURN_RATE      — Projects end-of-month spend from daily velocity vs budget
  ACCELERATION   — Flags categories spending >30% above 3-month rolling average
  MERCHANT_SPIKE — Statistically anomalous single transactions (z-score >= 2.5)
  CATEGORY_CREEP — Category budget share growing >= 8 ppts over 3 months
  SAVINGS_EROSION— Consecutive drops in savings or savings rate < 5%
  WEEKEND_DRAIN  — Weekend spending average >= 1.8x weekday average
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime, date
from flask_login import current_user

from ..extensions import db
from ..models.transaction import Transaction
from ..models.budget import Budget
from ..models.category import Category


# ── Alert dataclass ───────────────────────────────────────────────────────────
@dataclass
class Alert:
    alert_type: str          # burn_rate | acceleration | merchant_spike | creep | savings_erosion | weekend
    category: str
    month: str
    severity: str            # critical | warning | info
    headline: str            # short, punchy — shown in card title
    detail: str              # one concrete sentence with numbers
    action: str              # one specific thing to do about it
    amount: float            # the PKR figure being flagged
    pct_change: Optional[float] = None
    merchant: Optional[str] = None


ALERT_META = {
    "burn_rate":       {"icon": "🔥", "label": "Burn Rate",        "color": "#ef4444"},
    "acceleration":    {"icon": "📈", "label": "Spend Spike",      "color": "#f59e0b"},
    "merchant_spike":  {"icon": "🛒", "label": "Big Transaction",  "color": "#8b5cf6"},
    "creep":           {"icon": "🐢", "label": "Category Creep",   "color": "#f97316"},
    "savings_erosion": {"icon": "💸", "label": "Savings Dropping", "color": "#ec4899"},
    "weekend":         {"icon": "📅", "label": "Weekend Drain",    "color": "#06b6d4"},
}


def _get_user_transactions_df(user_id: int) -> pd.DataFrame:
    """Load user transactions into a pandas DataFrame for analysis."""
    transactions = (
        Transaction.query
        .filter_by(user_id=user_id, is_deleted=False, transaction_type='expense')
        .join(Category, Transaction.category_id == Category.category_id, isouter=True)
        .add_columns(
            Transaction.amount,
            Transaction.transaction_date,
            Transaction.description,
            Category.name.label('category_name')
        )
        .all()
    )

    if not transactions:
        return pd.DataFrame()

    rows = []
    for txn in transactions:
        rows.append({
            'amount': float(txn.amount),
            'date': txn.transaction_date.isoformat() if isinstance(txn.transaction_date, date) else str(txn.transaction_date),
            'description': txn.description or 'Unknown',
            'category': txn.category_name or 'Uncategorized',
        })

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df['month'] = df['date'].dt.to_period('M').astype(str)
    df['day_of_week'] = df['date'].dt.day_name()
    return df


def _get_user_budgets(user_id: int) -> Dict[str, float]:
    """Load user budgets as {category_name: monthly_limit}."""
    budgets = (
        Budget.query
        .filter_by(user_id=user_id)
        .join(Category, Budget.category_id == Category.category_id)
        .add_columns(Category.name.label('cat_name'), Budget.monthly_limit)
        .all()
    )
    return {b.cat_name: float(b.monthly_limit) for b in budgets}


def _monthly(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["month", "category"])["amount"]
        .sum().reset_index().rename(columns={"amount": "spent"})
        .sort_values("month")
    )


# ── Alert type 1: Burn Rate ──────────────────────────────────────────────────
def _burn_rate_alerts(df: pd.DataFrame, budgets: Dict[str, float]) -> List[Alert]:
    alerts = []
    if df.empty or not budgets:
        return alerts

    latest_month = df["month"].max()
    latest_df = df[df["month"] == latest_month]

    max_date = latest_df["date"].max()
    min_date = latest_df["date"].min()
    days_data = max((max_date - min_date).days + 1, 1)
    days_in_month = 30

    cat_spent = latest_df.groupby("category")["amount"].sum()
    for cat, spent in cat_spent.items():
        budget = budgets.get(cat)
        if not budget:
            continue
        daily_rate = spent / days_data
        projected = daily_rate * days_in_month
        pct_of_budget = projected / budget * 100

        if projected > budget * 1.5:
            severity = "critical"
            action = f"Cut {cat} spending by PKR {(projected-budget)/max(days_in_month-days_data,1):,.0f}/day to stay under budget."
        elif projected > budget:
            severity = "warning"
            action = f"You have {days_in_month - days_data} days left — limit {cat} to PKR {(budget - spent) / max(days_in_month - days_data, 1):,.0f}/day."
        else:
            continue

        alerts.append(Alert(
            alert_type="burn_rate", category=cat, month=latest_month,
            severity=severity,
            headline=f"{cat} on track for PKR {projected:,.0f} this month",
            detail=(
                f"Spent PKR {spent:,.0f} in {days_data} days "
                f"(PKR {daily_rate:,.0f}/day). "
                f"Projected month-end: PKR {projected:,.0f} vs PKR {budget:,.0f} budget."
            ),
            action=action, amount=projected, pct_change=pct_of_budget,
        ))
    return alerts


# ── Alert type 2: Spending Acceleration ──────────────────────────────────────
def _acceleration_alerts(df: pd.DataFrame, threshold_pct: float = 30.0) -> List[Alert]:
    alerts = []
    monthly = _monthly(df)
    if monthly.empty:
        return alerts
    latest_month = df["month"].max()

    for cat, grp in monthly.groupby("category"):
        grp = grp.sort_values("month")
        if len(grp) < 4:
            continue
        prev_3_avg = grp.iloc[-4:-1]["spent"].mean()
        latest_val = grp.iloc[-1]["spent"]
        if prev_3_avg < 100:
            continue
        pct = (latest_val - prev_3_avg) / prev_3_avg * 100

        if pct >= 60:
            severity = "critical"
        elif pct >= threshold_pct:
            severity = "warning"
        else:
            continue

        alerts.append(Alert(
            alert_type="acceleration", category=cat, month=latest_month,
            severity=severity,
            headline=f"{cat} up {pct:.0f}% vs your 3-month average",
            detail=(
                f"Last month: PKR {latest_val:,.0f}. "
                f"Previous 3-month average: PKR {prev_3_avg:,.0f}. "
                f"That's PKR {latest_val - prev_3_avg:,.0f} extra."
            ),
            action=f"Review {cat} transactions — look for a new subscription, habit, or one-off splurge.",
            amount=latest_val - prev_3_avg, pct_change=pct,
        ))
    return alerts


# ── Alert type 3: Merchant Spike ─────────────────────────────────────────────
def _merchant_spike_alerts(df: pd.DataFrame, z_threshold: float = 2.5) -> List[Alert]:
    alerts = []
    if df.empty:
        return alerts
    latest_month = df["month"].max()
    latest_df = df[df["month"] == latest_month]

    for cat, grp in df.groupby("category"):
        if len(grp) < 10:
            continue
        mean = grp["amount"].mean()
        std = grp["amount"].std()
        if std < 1:
            continue
        latest_cat = latest_df[latest_df["category"] == cat]
        for _, row in latest_cat.iterrows():
            z = (row["amount"] - mean) / std
            if z >= z_threshold:
                severity = "critical" if z >= 3.5 else "warning"
                alerts.append(Alert(
                    alert_type="merchant_spike", category=cat, month=latest_month,
                    severity=severity,
                    headline=f"Unusual PKR {row['amount']:,.0f} at {row['description']}",
                    detail=(
                        f"This transaction is {z:.1f}× above your usual {cat} spend "
                        f"(avg PKR {mean:,.0f}, std PKR {std:,.0f})."
                    ),
                    action="Verify this was intentional — if not, dispute with your bank.",
                    amount=row["amount"],
                    pct_change=(row["amount"] / mean - 1) * 100,
                    merchant=str(row["description"]),
                ))
    return alerts


# ── Alert type 4: Category Creep ─────────────────────────────────────────────
def _creep_alerts(df: pd.DataFrame, creep_threshold_ppt: float = 8.0) -> List[Alert]:
    alerts = []
    monthly = _monthly(df)
    months = sorted(df["month"].unique())
    if len(months) < 4:
        return []

    latest_month = months[-1]
    monthly_total = monthly.groupby("month")["spent"].sum().rename("total")
    monthly = monthly.join(monthly_total, on="month")
    monthly["share_pct"] = monthly["spent"] / monthly["total"] * 100

    for cat, grp in monthly.groupby("category"):
        grp = grp.sort_values("month")
        if len(grp) < 4:
            continue
        share_3m_ago = grp.iloc[-4]["share_pct"]
        share_now = grp.iloc[-1]["share_pct"]
        delta = share_now - share_3m_ago

        if delta >= creep_threshold_ppt:
            alerts.append(Alert(
                alert_type="creep", category=cat, month=latest_month,
                severity="warning",
                headline=f"{cat} grew from {share_3m_ago:.0f}% → {share_now:.0f}% of your budget",
                detail=(
                    f"3 months ago {cat} was {share_3m_ago:.1f}% of total spend. "
                    f"It's now {share_now:.1f}% — a {delta:.1f} percentage-point creep."
                ),
                action=f"Set a hard monthly cap for {cat} and review weekly.",
                amount=grp.iloc[-1]["spent"], pct_change=delta,
            ))
    return alerts


# ── Alert type 5: Savings Erosion ────────────────────────────────────────────
def _savings_erosion_alerts(df: pd.DataFrame, monthly_income: float = 80000) -> List[Alert]:
    alerts = []
    monthly = _monthly(df)
    sav = monthly[monthly["category"] == "Savings"].sort_values("month")
    if len(sav) < 3:
        return []

    latest_month = df["month"].max()
    last_3 = sav.iloc[-3:]["spent"].tolist()

    consecutive_drops = all(last_3[i] > last_3[i+1] for i in range(len(last_3)-1))
    savings_rate = sav.iloc[-1]["spent"] / monthly_income * 100

    if consecutive_drops:
        drop_pct = (last_3[0] - last_3[-1]) / last_3[0] * 100 if last_3[0] > 0 else 0
        alerts.append(Alert(
            alert_type="savings_erosion", category="Savings", month=latest_month,
            severity="critical" if savings_rate < 10 else "warning",
            headline=f"Savings dropped 3 months in a row — now PKR {last_3[-1]:,.0f}/month",
            detail=(
                f"3 months ago: PKR {last_3[0]:,.0f} → PKR {last_3[1]:,.0f} → PKR {last_3[2]:,.0f}. "
                f"Down {drop_pct:.0f}% overall. "
                f"Current savings rate: {savings_rate:.1f}% (target: 20%)."
            ),
            action="Set a standing transfer on payday before you can spend — even PKR 2,000/month compounds significantly.",
            amount=last_3[-1], pct_change=-drop_pct,
        ))
    elif savings_rate < 5:
        alerts.append(Alert(
            alert_type="savings_erosion", category="Savings", month=latest_month,
            severity="critical",
            headline=f"Savings rate critically low at {savings_rate:.1f}%",
            detail=(
                f"Saving only PKR {sav.iloc[-1]['spent']:,.0f} against PKR {monthly_income:,.0f} income. "
                f"Recommended minimum: PKR {monthly_income * 0.20:,.0f} (20%)."
            ),
            action="Automate PKR 5,000/month minimum to a separate savings account.",
            amount=sav.iloc[-1]["spent"], pct_change=savings_rate - 20,
        ))
    return alerts


# ── Alert type 6: Weekend Drain ──────────────────────────────────────────────
def _weekend_drain_alert(df: pd.DataFrame, ratio_threshold: float = 1.8) -> List[Alert]:
    if "day_of_week" not in df.columns or df.empty:
        return []
    alerts = []
    weekend = {"Saturday", "Sunday"}
    latest_month = df["month"].max()
    df_latest = df[df["month"] == latest_month].copy()

    df_latest["is_weekend"] = df_latest["day_of_week"].isin(weekend)
    weekend_data = df_latest[df_latest["is_weekend"]]["amount"]
    weekday_data = df_latest[~df_latest["is_weekend"]]["amount"]

    if weekend_data.empty or weekday_data.empty:
        return []

    weekend_avg = weekend_data.mean()
    weekday_avg = weekday_data.mean()

    if weekday_avg < 1 or weekend_avg < 1:
        return []
    ratio = weekend_avg / weekday_avg

    if ratio >= ratio_threshold:
        extra_per_month = (weekend_avg - weekday_avg) * 8
        severity = "critical" if ratio >= 3.0 else "warning"
        alerts.append(Alert(
            alert_type="weekend", category="Miscellaneous", month=latest_month,
            severity=severity,
            headline=f"Weekend spending {ratio:.1f}× higher than weekdays",
            detail=(
                f"Average weekend transaction: PKR {weekend_avg:,.0f} vs "
                f"PKR {weekday_avg:,.0f} on weekdays. "
                f"That's roughly PKR {extra_per_month:,.0f}/month in weekend premium."
            ),
            action="Plan weekend activities in advance with a fixed cash envelope.",
            amount=extra_per_month, pct_change=(ratio - 1) * 100,
        ))
    return alerts


# ── Public API ────────────────────────────────────────────────────────────────
def detect_overspending(user_id: int, monthly_income: float = 80000) -> List[Alert]:
    """Run all 6 alert engines on the given user's transaction history.

    Returns alerts sorted by severity (critical first), then by amount descending.
    """
    df = _get_user_transactions_df(user_id)
    if df.empty:
        return []

    budgets = _get_user_budgets(user_id)

    alerts: List[Alert] = []
    alerts += _burn_rate_alerts(df, budgets)
    alerts += _acceleration_alerts(df, threshold_pct=30.0)
    alerts += _merchant_spike_alerts(df, z_threshold=2.5)
    alerts += _creep_alerts(df, creep_threshold_ppt=8.0)
    alerts += _savings_erosion_alerts(df, monthly_income)
    alerts += _weekend_drain_alert(df, ratio_threshold=1.8)

    # Deduplicate
    seen = set()
    deduped = []
    for a in alerts:
        key = (a.alert_type, a.category, a.month)
        if key not in seen:
            seen.add(key)
            deduped.append(a)

    sev_order = {"critical": 0, "warning": 1, "info": 2}
    deduped.sort(key=lambda a: (sev_order.get(a.severity, 3), -a.amount))
    return deduped


def get_alerts_json(user_id: int, monthly_income: float = 80000) -> list:
    """Return alerts as JSON-serializable list of dicts."""
    alerts = detect_overspending(user_id, monthly_income)
    result = []
    for a in alerts:
        meta = ALERT_META.get(a.alert_type, {})
        result.append({
            'type': a.alert_type,
            'icon': meta.get('icon', '⚠️'),
            'label': meta.get('label', a.alert_type),
            'color': meta.get('color', '#6b7280'),
            'category': a.category,
            'severity': a.severity,
            'headline': a.headline,
            'detail': a.detail,
            'action': a.action,
            'amount': a.amount,
            'pct_change': a.pct_change,
            'merchant': a.merchant,
        })
    return result
