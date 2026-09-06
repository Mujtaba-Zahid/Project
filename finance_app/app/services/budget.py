"""Budget checking and overspend alert service."""
from datetime import date
from calendar import monthrange
from ..extensions import db
from ..models.budget import Budget
from ..models.transaction import Transaction
from ..models.category import Category
from .notifications import create_notification


def _month_range(month_start):
    """Return (first_day, last_day) for a month given its first day."""
    _, last_day = monthrange(month_start.year, month_start.month)
    return month_start, date(month_start.year, month_start.month, last_day)


def _get_spending(user_id, category_id, month):
    """Get total spending for a category in a given month (cross-DB)."""
    first, last = _month_range(month)
    spent = db.session.query(
        db.func.coalesce(db.func.sum(Transaction.amount), 0)
    ).filter(
        Transaction.user_id == user_id,
        Transaction.category_id == category_id,
        Transaction.transaction_type == 'expense',
        Transaction.is_deleted == False,  # noqa: E712
        Transaction.transaction_date >= first,
        Transaction.transaction_date <= last,
    ).scalar()
    return float(spent)


def get_budget_status(user_id, month=None):
    """Get all budgets for a user with actual spending for the month."""
    if month is None:
        month = date.today().replace(day=1)

    budgets = Budget.query.filter_by(user_id=user_id, month=month).all()
    results = []

    for budget in budgets:
        spent = _get_spending(user_id, budget.category_id, month)
        limit = float(budget.monthly_limit)
        threshold = float(budget.alert_threshold)

        results.append({
            'budget': budget,
            'category': db.session.get(Category, budget.category_id),
            'spent': spent,
            'remaining': limit - spent,
            'percentage': round(spent / limit * 100, 1) if limit > 0 else 0,
            'over_budget': spent > limit,
            'near_budget': spent >= (limit * threshold) and spent <= limit,
        })

    return results


def check_and_alert(user_id, category_id, month=None):
    """Check if a budget is exceeded and send alert if not already sent."""
    if month is None:
        month = date.today().replace(day=1)

    budget = Budget.query.filter_by(
        user_id=user_id, category_id=category_id, month=month
    ).first()

    if not budget:
        return

    spent = _get_spending(user_id, category_id, month)
    limit = float(budget.monthly_limit)
    threshold = float(budget.alert_threshold)

    if spent >= (limit * threshold) and not budget.alert_sent:
        category = db.session.get(Category, category_id)
        cat_name = category.name if category else 'Unknown'

        create_notification(
            user_id=user_id,
            notif_type='budget_alert',
            title=f'Budget Alert: {cat_name}',
            message=f'You have spent {spent:,.0f} of your {limit:,.0f} budget for {cat_name}. '
                    f'That is {spent/limit*100:.0f}% of your monthly limit.',
        )

        budget.alert_sent = True
        db.session.commit()
