from datetime import date, timedelta
from calendar import monthrange
from flask import render_template, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import func, case, extract
from . import dashboard_bp
from ..extensions import db
from ..models.transaction import Transaction
from ..models.account import Account
from ..models.budget import Budget
from ..models.category import Category
from ..models.savings_goal import SavingsGoal
from ..models.investment import Investment
from ..services.budget import get_budget_status
from ..services.notifications import get_unread_count
from ..services.ai_alerts import get_alerts_json


def _month_range(year, month):
    """Return (first_day, last_day) for a given year/month."""
    first = date(year, month, 1)
    _, last_day = monthrange(year, month)
    last = date(year, month, last_day)
    return first, last


@dashboard_bp.route('/')
@login_required
def index():
    user_id = current_user.user_id
    today = date.today()
    month_start, month_end = _month_range(today.year, today.month)

    # KPI: Total balance across all active accounts
    total_balance = _get_total_balance(user_id)

    # KPI: Monthly income / expense
    monthly_income, monthly_expense = _get_monthly_totals(user_id, month_start, month_end)

    # KPI: Net worth (balances + investments)
    investment_value = db.session.query(
        func.coalesce(func.sum(Investment.current_value), 0)
    ).filter(
        Investment.user_id == user_id,
        Investment.sold_date.is_(None),
    ).scalar()
    net_worth = total_balance + float(investment_value)

    # Recent transactions
    recent_transactions = Transaction.query.filter_by(
        user_id=user_id, is_deleted=False
    ).order_by(Transaction.transaction_date.desc()).limit(10).all()

    # Budget status
    budget_status = get_budget_status(user_id, month_start)

    # Savings goals
    savings_goals = SavingsGoal.query.filter_by(
        user_id=user_id, is_deleted=False
    ).filter(SavingsGoal.status == 'active').all()

    # Accounts
    accounts = Account.query.filter_by(
        user_id=user_id, is_deleted=False, is_active=True
    ).all()

    # Notification count
    notif_count = get_unread_count(user_id)

    # AI alerts for dashboard banner
    try:
        ai_alerts = get_alerts_json(user_id)[:3]
    except Exception:
        ai_alerts = []

    return render_template('dashboard/index.html',
                           total_balance=total_balance,
                           monthly_income=monthly_income,
                           monthly_expense=monthly_expense,
                           net_worth=net_worth,
                           recent_transactions=recent_transactions,
                           budget_status=budget_status,
                           savings_goals=savings_goals,
                           accounts=accounts,
                           notif_count=notif_count,
                           ai_alerts=ai_alerts)


@dashboard_bp.route('/chart/income-expense')
@login_required
def chart_income_expense():
    """Return 6-month income vs expense data for Chart.js."""
    user_id = current_user.user_id
    today = date.today()
    months = []
    income_data = []
    expense_data = []

    for i in range(5, -1, -1):
        # Walk back i months
        m = today.month - i
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        first, last = _month_range(y, m)
        label = first.strftime('%b %Y')
        months.append(label)

        income = db.session.query(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == 'income',
            Transaction.is_deleted == False,
            Transaction.transaction_date >= first,
            Transaction.transaction_date <= last,
        ).scalar()

        expense = db.session.query(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == 'expense',
            Transaction.is_deleted == False,
            Transaction.transaction_date >= first,
            Transaction.transaction_date <= last,
        ).scalar()

        income_data.append(float(income))
        expense_data.append(float(expense))

    return jsonify({
        'labels': months,
        'income': income_data,
        'expense': expense_data,
    })


@dashboard_bp.route('/chart/spending-category')
@login_required
def chart_spending_category():
    """Return current month spending by category for Chart.js doughnut."""
    user_id = current_user.user_id
    today = date.today()
    first, last = _month_range(today.year, today.month)

    results = db.session.query(
        Category.name,
        func.sum(Transaction.amount).label('total')
    ).join(Transaction, Transaction.category_id == Category.category_id).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'expense',
        Transaction.is_deleted == False,
        Transaction.transaction_date >= first,
        Transaction.transaction_date <= last,
    ).group_by(Category.name).order_by(func.sum(Transaction.amount).desc()).all()

    return jsonify({
        'labels': [r[0] for r in results],
        'data': [float(r[1]) for r in results],
    })


def _get_total_balance(user_id):
    """Compute total balance across all active accounts."""
    result = db.session.query(
        func.coalesce(func.sum(
            case(
                (Transaction.transaction_type == 'income', Transaction.amount),
                else_=-Transaction.amount
            )
        ), 0)
    ).join(Account, Account.account_id == Transaction.account_id).filter(
        Transaction.user_id == user_id,
        Transaction.is_deleted == False,
        Account.is_deleted == False,
        Account.is_active == True,
    ).scalar()
    return float(result)


def _get_monthly_totals(user_id, month_start, month_end):
    """Get monthly income and expense totals using date range (cross-DB)."""
    income = db.session.query(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'income',
        Transaction.is_deleted == False,
        Transaction.transaction_date >= month_start,
        Transaction.transaction_date <= month_end,
    ).scalar()

    expense = db.session.query(
        func.coalesce(func.sum(Transaction.amount), 0)
    ).filter(
        Transaction.user_id == user_id,
        Transaction.transaction_type == 'expense',
        Transaction.is_deleted == False,
        Transaction.transaction_date >= month_start,
        Transaction.transaction_date <= month_end,
    ).scalar()

    return float(income), float(expense)
