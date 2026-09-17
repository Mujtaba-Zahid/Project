"""
services/recommender.py — Smart Product-Aware Recommendation Engine
───────────────────────────────────────────────────────────────────
Two layers:
  1. Rule-based pattern analysis → SPECIFIC Pakistani product/service alternatives
  2. build_groq_context() → feeds user's full financial data to Groq chatbot
"""

import pandas as pd
import numpy as np
from typing import List, Dict
from dataclasses import dataclass, field
from datetime import date

from ..extensions import db
from ..models.transaction import Transaction
from ..models.category import Category
from ..models.financial_profile import FinancialProfile


# ── Product substitution database (Pakistani market) ─────────────────────────
SUBSTITUTIONS: Dict[str, Dict] = {
    "netflix": {
        "label": "Netflix",
        "alternatives": [
            ("YouTube Premium Family", "PKR 540/mo shared", "split among 5 = PKR 108/person"),
            ("Tapmad TV", "PKR 250/mo", "local Pakistani content + sports"),
            ("Rotate + cancel model", "~50% saving", "subscribe 1 month, binge, cancel"),
        ],
        "saving_tip": "Downgrade to mobile-only plan or share a family plan to cut cost 75%."
    },
    "spotify": {
        "label": "Spotify",
        "alternatives": [
            ("YouTube Music free", "PKR 0", "same library with ads"),
            ("Spotify Student/Family", "PKR 230/mo", "50% off with family sharing"),
            ("JioSaavn", "PKR 99/mo", "large South Asian library"),
        ],
        "saving_tip": "Spotify free with data saver mode costs nothing. Family plan = PKR 58/person."
    },
    "uber": {
        "label": "Uber",
        "alternatives": [
            ("InDrive", "~30% cheaper", "you negotiate the fare, no surge pricing"),
            ("Bykea", "PKR 30–100/trip", "motorcycle, fastest for short hops"),
            ("BRT / MetroBus pass", "PKR 1,500/mo", "unlimited rides"),
        ],
        "saving_tip": "InDrive bids routinely come in 25–35% below Uber for the same route."
    },
    "careem": {
        "label": "Careem",
        "alternatives": [
            ("InDrive", "~25–35% cheaper", "bid-based, lower surge pricing"),
            ("Bykea", "PKR 30–100/trip", "motorcycle, fastest for distances under 5km"),
            ("MetroBus / BRT", "PKR 20–30/trip", "fixed route but very cheap"),
        ],
        "saving_tip": "Careem Go is significantly cheaper than Careem Go+ — always pick base tier."
    },
    "mcdonald": {
        "label": "McDonald's",
        "alternatives": [
            ("Local broast house", "40–60% cheaper", "comparable quality, no brand markup"),
            ("Student Biryani", "PKR 150–300/meal", "full meal vs PKR 800+ at McDonald's"),
            ("Meal prep at home", "PKR 50–100/meal", "batch cook on Sundays"),
        ],
        "saving_tip": "McDonald's app has daily deals — always order via app, prices are 15–20% lower."
    },
    "kfc": {
        "label": "KFC",
        "alternatives": [
            ("Local broast restaurant", "50% cheaper", "local broast is genuinely excellent"),
            ("KFC Tuesday deal only", "PKR 299 combo", "cheapest day — plan meals around it"),
            ("Air-fryer broast at home", "PKR 80–150/meal", "replicate KFC results at home"),
        ],
        "saving_tip": "KFC Tuesday is the best value fast-food deal in Pakistan — limit visits to Tuesdays."
    },
    "daraz": {
        "label": "Daraz",
        "alternatives": [
            ("OLX Pakistan", "used items 40–70% off", "electronics, furniture, clothes"),
            ("Daraz 11.11 / Big Friday", "up to 70% off", "plan big purchases around sales"),
            ("AliExpress direct", "10–30% cheaper", "same suppliers, no middleman"),
        ],
        "saving_tip": "Add to Daraz wishlist and wait for Flash Sale — items regularly drop 20–50%."
    },
    "pharmacy": {
        "label": "Pharmacy",
        "alternatives": [
            ("Generic medicines", "40–80% cheaper", "same molecule — ask pharmacist"),
            ("Government dispensary", "PKR 0–50", "free or near-free for common meds"),
            ("Dawaai.pk", "10–25% cheaper", "delivery + verified generics"),
        ],
        "saving_tip": "Generic paracetamol (PKR 12) = Panadol (PKR 80). Always ask for generics."
    },
    "jazz": {
        "label": "Jazz (Mobile/Internet)",
        "alternatives": [
            ("Jazz Giga Max weekly", "PKR 55/week", "14GB — better per-GB value"),
            ("Zong 4G unlimited", "PKR 500/mo", "compare speeds in your area"),
            ("PTCL Fiber + minimal mobile data", "combo approach", "fiber at home, low data out"),
        ],
        "saving_tip": "Jazz weekly bundles are consistently cheaper per GB than monthly packs."
    },
}

CATEGORY_TIPS: Dict[str, List[str]] = {
    "Food & Dining": [
        "Meal prep Sundays: cooking 5 portions at once cuts per-meal cost 60–70%.",
        "FoodPanda/Cheetay Happy Hours (10pm–midnight) give 30–50% off.",
        "Buy staples from Imtiaz/Metro rather than neighbourhood kiryana — 20–30% cheaper.",
    ],
    "Transport": [
        "BRT/MetroBus monthly pass = PKR 1,500 unlimited — breaks even in ~5 Careem trips.",
        "Consolidate errands: one trip covering 3 tasks beats 3 separate ride-hail trips.",
        "Carpool with colleagues: splitting fuel 3 ways cuts your cost to PKR 33/trip.",
    ],
    "Entertainment": [
        "Audit all subscriptions — average person pays for 2–3 they forgot about.",
        "YouTube free + uBlock Origin = zero cost for most content.",
        "Family plan sharing: split Netflix/Spotify 4 ways = PKR 100–200/person/month.",
    ],
    "Shopping": [
        "72-hour rule: wait 3 days before any purchase over PKR 3,000.",
        "OLX/Facebook Marketplace: 50–80% off lightly used electronics and furniture.",
        "Buy off-season: winter clothes in March, summer in October — 40–60% discounts.",
    ],
    "Utilities": [
        "LED bulbs cut electricity 70–80% per light point vs CFL/incandescent.",
        "Phantom load (standby devices) = 5–10% of your KESC bill — unplug everything.",
    ],
    "Healthcare": [
        "Generic medicines are chemically identical to branded — always ask for generics.",
        "Annual check-up (PKR 3,000) prevents expensive emergency treatments.",
    ],
    "Savings": [
        "Automate savings: standing transfer on payday — before you can spend it.",
        "National Savings Certificates: 15–21% annual returns, government-backed.",
        "Meezan Bank Savings: ~13% profit rate, Shariah-compliant, easy access.",
    ],
}


@dataclass
class Recommendation:
    title: str
    detail: str
    category: str
    priority: str              # high | medium | low
    potential_saving: float     # estimated PKR annual saving
    substitutions: List[tuple] = field(default_factory=list)
    merchants_detected: List[str] = field(default_factory=list)


def _get_user_df(user_id: int) -> pd.DataFrame:
    """Load user expense transactions as a DataFrame."""
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
    return df


def _detect_merchants(descriptions: pd.Series) -> Dict[str, int]:
    counts = {}
    for key in SUBSTITUTIONS:
        n = int(descriptions.str.lower().str.contains(key, na=False).sum())
        if n > 0:
            counts[key] = n
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def generate_recommendations(user_id: int, monthly_income: float = 80000) -> List[Recommendation]:
    """Generate personalized PKR savings recommendations for the user."""
    from ..services.ai_alerts import _get_user_budgets

    df = _get_user_df(user_id)
    if df.empty:
        return _fallback_recommendations()

    budgets = _get_user_budgets(user_id)
    recs: List[Recommendation] = []
    months = max(df["month"].nunique(), 1)
    cat_totals = df.groupby("category")["amount"].sum()
    monthly_avg = df.groupby("month")["amount"].sum().mean()
    merchant_hits = _detect_merchants(df["description"])

    # R1: Merchant-specific substitutions
    for merchant_key, txn_count in merchant_hits.items():
        info = SUBSTITUTIONS[merchant_key]
        subset = df[df["description"].str.lower().str.contains(merchant_key, na=False)]
        cat = subset["category"].mode().iloc[0] if len(subset) else "Miscellaneous"
        avg_per_month = subset["amount"].sum() / months

        recs.append(Recommendation(
            title=f"Switch from {info['label']} to these cheaper alternatives",
            detail=info["saving_tip"],
            category=cat,
            priority="high" if avg_per_month > 1500 else "medium",
            potential_saving=avg_per_month * 0.40 * 12,
            substitutions=info["alternatives"],
            merchants_detected=[info["label"]],
        ))

    # R2: Category budget recommendations
    for cat, budget in budgets.items():
        cat_monthly = df[df["category"] == cat].groupby("month")["amount"].sum()
        if len(cat_monthly) == 0:
            continue
        avg = cat_monthly.mean()
        if avg > budget and cat in CATEGORY_TIPS:
            tip = CATEGORY_TIPS[cat][len(recs) % len(CATEGORY_TIPS[cat])]
            recs.append(Recommendation(
                title=f"Bring {cat} under PKR {budget:,.0f}/month",
                detail=tip,
                category=cat,
                priority="high",
                potential_saving=(avg - budget) * 12,
            ))

    # R3: Savings target
    savings_total = cat_totals.get("Savings", 0)
    savings_rate = savings_total / (monthly_income * months)
    if savings_rate < 0.20:
        target = monthly_income * 0.20
        current = savings_total / months
        monthly_gap = target - current
        recs.append(Recommendation(
            title=f"Invest PKR {target:,.0f}/month to hit the 20% savings target",
            detail=(
                f"Start with PKR {min(monthly_gap, 5000):,.0f}/month via a standing transfer. "
                f"NSCs pay 21% annually — your savings compound significantly."
            ),
            category="Savings",
            priority="high",
            potential_saving=monthly_gap * 12,
            substitutions=[
                ("National Savings Certificates", "21% p.a.", "safest, government-backed"),
                ("Meezan Savings Account", "~13% p.a.", "Shariah-compliant, easy access"),
            ],
        ))

    # Ensure at least 3 recommendations
    fallbacks = _fallback_recommendations()
    i = 0
    while len(recs) < 3 and i < len(fallbacks):
        recs.append(fallbacks[i])
        i += 1

    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: (order.get(r.priority, 2), -r.potential_saving))
    return recs


def _fallback_recommendations() -> List[Recommendation]:
    return [
        Recommendation(
            title="Apply the 72-hour rule to purchases over PKR 3,000",
            detail="Add the item to a wishlist and wait 3 days before buying. Eliminates 30–40% of impulse buys.",
            category="Shopping", priority="medium", potential_saving=15000,
        ),
        Recommendation(
            title="Ask your pharmacist for generics — same drug, 40–80% cheaper",
            detail="Generic paracetamol (PKR 12) = Panadol (PKR 80). Works for 90% of common prescriptions.",
            category="Healthcare", priority="low", potential_saving=8000,
            substitutions=[
                ("Generic paracetamol", "PKR 12", "identical to Panadol"),
                ("Dawaai.pk online", "10–25% off", "verified generics with home delivery"),
            ],
        ),
        Recommendation(
            title="Consolidate streaming subscriptions to save 50%",
            detail="Subscribe to one service at a time, binge, cancel, rotate. Or share a family plan.",
            category="Entertainment", priority="medium", potential_saving=12000,
        ),
    ]


def build_groq_context(user_id: int) -> str:
    """Build rich system prompt for the Groq Finance Chatbot.

    Includes full spending history + Kaggle-enriched financial health profile.
    """
    df = _get_user_df(user_id)
    profile = FinancialProfile.query.filter_by(user_id=user_id).first()
    monthly_income = profile.monthly_income_pkr if profile else 80000

    lines = [
        "You are an expert personal finance advisor specialising in the Pakistani market (PKR).",
        "You have the user's COMPLETE spending history AND financial health profile. Use both.",
        "Give SPECIFIC, named alternatives — never generic advice.",
        "Always name real Pakistani products, brands, stores, apps with real PKR prices.",
        "Be conversational and direct. Use bullet points for alternatives. Keep answers under 180 words.",
        "",
        "=== FINANCIAL HEALTH PROFILE ===",
        f"Monthly income     : PKR {monthly_income:,.0f}",
    ]

    if profile:
        p = profile.to_dict()
        cs = p.get("credit_score", 680)
        dti = p.get("debt_to_income_ratio", 0.35)
        sr = p.get("savings_rate", 0.10)
        sl = p.get("financial_stress_level", "Medium")
        cf = p.get("cash_flow_status", "Neutral")
        efm = p.get("emergency_fund_months", 1.0)
        it = p.get("income_type", "Salary")
        lines += [
            f"Income type        : {it}",
            f"Credit score       : {cs} ({'Good' if cs>=720 else 'Fair' if cs>=650 else 'Poor'})",
            f"Debt-to-income     : {dti:.0%} ({'OK' if dti<0.30 else 'High' if dti>0.45 else 'Moderate'})",
            f"Savings rate       : {sr:.0%} ({'On track' if sr>=0.20 else 'Below target'})",
            f"Financial stress   : {sl}",
            f"Cash flow          : {cf}",
            f"Emergency fund     : {efm:.1f} months ({'Sufficient' if efm>=3 else 'Insufficient'})",
            f"Advice score       : {p.get('financial_advice_score', 50)}/100",
        ]
        if sl == "High":
            lines.append("⚠️ USER IS UNDER HIGH FINANCIAL STRESS — be empathetic and focus on quick wins.")
        if dti > 0.45:
            lines.append("⚠️ HIGH DEBT-TO-INCOME — prioritise debt reduction advice.")
        if efm < 1:
            lines.append("⚠️ NO EMERGENCY FUND — flag this as urgent.")

    if not df.empty:
        cat_summary = df.groupby("category")["amount"].agg(["sum", "count"])
        total_spent = df["amount"].sum()

        lines += ["", "=== SPENDING BY CATEGORY ==="]
        for cat, row in cat_summary.iterrows():
            pct = row["sum"] / total_spent * 100 if total_spent else 0
            lines.append(f"  {cat}: PKR {row['sum']:,.0f} ({pct:.1f}%) — {int(row['count'])} txns")

        top_merchants = df.groupby("description")["amount"].agg(["sum", "count"]).nlargest(10, "sum")
        lines += ["", "=== TOP 10 MERCHANTS ==="]
        for desc, row in top_merchants.iterrows():
            lines.append(f"  {desc}: PKR {row['sum']:,.0f} ({int(row['count'])} visits)")

        merchant_hits = _detect_merchants(df["description"])
        if merchant_hits:
            lines += ["", "=== MERCHANTS WITH CHEAPER ALTERNATIVES ==="]
            for m, count in list(merchant_hits.items())[:8]:
                info = SUBSTITUTIONS[m]
                lines.append(f"  {info['label']}: {count} transactions")

    return "\n".join(lines)
