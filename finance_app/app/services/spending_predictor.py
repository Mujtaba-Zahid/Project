"""
services/spending_predictor.py — ML Spending Predictor
──────────────────────────────────────────────────────
15-feature GradientBoostingRegressor pipeline adapted for SQLAlchemy data.

Features: cat_encoded, month_ord, month_sin, month_cos,
          num_transactions, avg_transaction, max_transaction,
          lag_1, lag_2, lag_3, rolling_mean_3, rolling_std_3,
          lag1_zscore, cat_share, spend_momentum

Split: Chronological 80/20 (prevents temporal data leakage).
"""

import os
import pickle
import logging
from typing import Dict, Tuple, Optional
from datetime import date

import pandas as pd
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from ..extensions import db
from ..models.transaction import Transaction
from ..models.category import Category

logger = logging.getLogger(__name__)

# Model artifact directory (relative to app instance)
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'ml_models')

FEATURE_COLS = [
    "cat_encoded", "month_ord", "month_sin", "month_cos",
    "num_transactions", "avg_transaction", "max_transaction",
    "lag_1", "lag_2", "lag_3",
    "rolling_mean_3", "rolling_std_3",
    "lag1_zscore", "cat_share", "spend_momentum",
]


def _get_expense_df(user_id: int) -> pd.DataFrame:
    """Load expense transactions for ML processing."""
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


def _build_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, LabelEncoder]:
    """Aggregate to monthly category level and engineer 15 features."""
    le = LabelEncoder()
    df = df.copy()
    df["cat_encoded"] = le.fit_transform(df["category"])

    monthly = (
        df.groupby(["month", "category", "cat_encoded"])
        .agg(
            total_spent=("amount", "sum"),
            num_transactions=("amount", "count"),
            avg_transaction=("amount", "mean"),
            max_transaction=("amount", "max"),
        )
        .reset_index()
    )

    monthly["month_ord"] = (
        pd.to_datetime(monthly["month"]).dt.year * 12
        + pd.to_datetime(monthly["month"]).dt.month
    )

    monthly = monthly.sort_values(["category", "month_ord"]).reset_index(drop=True)

    # Cyclical month encoding
    month_of_year = ((monthly["month_ord"] - 1) % 12) + 1
    monthly["month_sin"] = np.sin(2 * np.pi * month_of_year / 12)
    monthly["month_cos"] = np.cos(2 * np.pi * month_of_year / 12)

    # Lag features
    monthly["lag_1"] = monthly.groupby("category")["total_spent"].shift(1)
    monthly["lag_2"] = monthly.groupby("category")["total_spent"].shift(2)
    monthly["lag_3"] = monthly.groupby("category")["total_spent"].shift(3)

    # Rolling statistics
    monthly["rolling_mean_3"] = (
        monthly.groupby("category")["total_spent"]
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).mean())
    )
    monthly["rolling_std_3"] = (
        monthly.groupby("category")["total_spent"]
        .transform(lambda x: x.shift(1).rolling(3, min_periods=1).std().fillna(0))
    )

    # Derived features
    cat_mean = monthly.groupby("category")["lag_1"].transform("mean")
    cat_std = monthly.groupby("category")["lag_1"].transform("std").replace(0, 1)
    monthly["lag1_zscore"] = (monthly["lag_1"] - cat_mean) / cat_std

    monthly_total = monthly.groupby("month_ord")["total_spent"].transform("sum")
    monthly["cat_share"] = monthly["total_spent"] / monthly_total.replace(0, 1)

    monthly["spend_momentum"] = monthly["lag_1"] - monthly["lag_2"]

    monthly.dropna(inplace=True)
    monthly.reset_index(drop=True, inplace=True)

    return monthly, le


def train_models(user_id: int) -> Optional[Dict]:
    """Train ML models on user's transaction history.

    Returns dict with model metrics, or None if insufficient data.
    """
    df = _get_expense_df(user_id)
    if df.empty or df["month"].nunique() < 4:
        return None

    features_df, le = _build_features(df)
    if len(features_df) < 10:
        return None

    features_sorted = features_df.sort_values("month_ord").reset_index(drop=True)
    split_idx = int(len(features_sorted) * 0.80)

    X = features_sorted[FEATURE_COLS].values
    y = features_sorted["total_spent"].values

    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    if len(X_test) == 0:
        return None

    models = {
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=4,
            subsample=0.8, min_samples_leaf=3, random_state=42,
        ),
        "Random Forest": RandomForestRegressor(
            n_estimators=300, max_depth=8, min_samples_leaf=3,
            max_features=0.7, random_state=42,
        ),
    }

    results = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        results[name] = {
            "model": model,
            "MAE": round(mean_absolute_error(y_test, y_pred), 2),
            "RMSE": round(mean_squared_error(y_test, y_pred) ** 0.5, 2),
            "R2": round(r2_score(y_test, y_pred), 4),
        }

    # Persist best model
    best_name = max(results, key=lambda k: results[k]["R2"])
    best_model = results[best_name]["model"]

    os.makedirs(MODEL_DIR, exist_ok=True)
    model_path = os.path.join(MODEL_DIR, f'user_{user_id}_model.pkl')
    with open(model_path, "wb") as f:
        pickle.dump({
            "model": best_model,
            "encoder": le,
            "feature_cols": FEATURE_COLS,
            "best_name": best_name,
        }, f)

    return {
        name: {k: v for k, v in metrics.items() if k != 'model'}
        for name, metrics in results.items()
    }


def predict_next_month(user_id: int) -> Optional[pd.DataFrame]:
    """Predict next month's spending per category.

    Returns DataFrame with columns [category, predicted_next_month],
    or None if no model exists and insufficient data to train.
    """
    model_path = os.path.join(MODEL_DIR, f'user_{user_id}_model.pkl')

    df = _get_expense_df(user_id)
    if df.empty:
        return None

    if not os.path.exists(model_path):
        result = train_models(user_id)
        if result is None:
            return None

    try:
        with open(model_path, "rb") as f:
            artefact = pickle.load(f)
    except Exception as e:
        logger.error(f"Failed to load model for user {user_id}: {e}")
        return None

    model = artefact["model"]
    le = artefact["encoder"]
    f_cols = artefact["feature_cols"]

    features_df, _ = _build_features(df)
    if features_df.empty:
        return None

    latest = (
        features_df.sort_values("month_ord")
        .groupby("category")
        .last()
        .reset_index()
    )

    next_ord = latest["month_ord"] + 1
    month_of_year = ((next_ord - 1) % 12) + 1

    pred_input = latest.copy()
    pred_input["month_ord"] = next_ord
    pred_input["month_sin"] = np.sin(2 * np.pi * month_of_year / 12)
    pred_input["month_cos"] = np.cos(2 * np.pi * month_of_year / 12)
    pred_input["lag_3"] = latest["lag_2"]
    pred_input["lag_2"] = latest["lag_1"]
    pred_input["lag_1"] = latest["total_spent"]
    pred_input["rolling_mean_3"] = (latest["total_spent"] + latest["lag_1"] + latest["lag_2"]) / 3
    pred_input["rolling_std_3"] = latest[["total_spent", "lag_1", "lag_2"]].std(axis=1).fillna(0)
    pred_input["spend_momentum"] = latest["total_spent"] - latest["lag_1"]

    cat_mean = pred_input.groupby("category")["lag_1"].transform("mean")
    cat_std = pred_input.groupby("category")["lag_1"].transform("std").replace(0, 1)
    pred_input["lag1_zscore"] = (pred_input["lag_1"] - cat_mean) / cat_std
    pred_input["cat_share"] = latest["cat_share"]

    X_pred = pred_input[f_cols].copy()
    train_means = features_df[f_cols].mean()
    X_pred = X_pred.fillna(train_means).values
    preds = np.clip(model.predict(X_pred), 0, None)

    result = pred_input[["category"]].copy()
    result["predicted_next_month"] = np.round(preds, 2)
    return result.sort_values("predicted_next_month", ascending=False).reset_index(drop=True)
