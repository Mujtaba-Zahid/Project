import csv
import io
from datetime import date
from calendar import monthrange
from collections import defaultdict
from flask import render_template, request, Response
from flask_login import login_required, current_user
from sqlalchemy import func, case
from . import reports_bp
from ..extensions import db
from ..models.transaction import Transaction
from ..models.category import Category
from ..models.audit_log import AuditLog


@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html')


@reports_bp.route('/monthly')
@login_required
def monthly():
    """Monthly income vs expense summary (cross-DB compatible)."""
    transactions = Transaction.query.filter_by(
        user_id=current_user.user_id, is_deleted=False
    ).order_by(Transaction.transaction_date.desc()).all()

    # Group by month in Python (avoids date_trunc)
    month_data = defaultdict(lambda: {'income': 0, 'expense': 0})
    for txn in transactions:
        key = txn.transaction_date.replace(day=1)
        if txn.transaction_type == 'income':
            month_data[key]['income'] += float(txn.amount)
        else:
            month_data[key]['expense'] += float(txn.amount)

    data = []
    for month_key in sorted(month_data.keys(), reverse=True):
        vals = month_data[month_key]
        data.append({
            'month': month_key.strftime('%B %Y'),
            'income': vals['income'],
            'expense': vals['expense'],
            'savings': vals['income'] - vals['expense'],
        })

    return render_template('reports/monthly.html', data=data)


@reports_bp.route('/category')
@login_required
def category_breakdown():
    """Spending breakdown by category."""
    results = db.session.query(
        Category.name,
        Category.icon,
        func.sum(Transaction.amount).label('total'),
        func.count(Transaction.transaction_id).label('count'),
        func.round(func.avg(Transaction.amount), 2).label('avg'),
    ).join(Transaction, Transaction.category_id == Category.category_id).filter(
        Transaction.user_id == current_user.user_id,
        Transaction.transaction_type == 'expense',
        Transaction.is_deleted == False,
    ).group_by(Category.name, Category.icon).order_by(func.sum(Transaction.amount).desc()).all()

    data = [{
        'name': r.name,
        'icon': r.icon,
        'total': float(r.total),
        'count': r.count,
        'avg': float(r.avg) if r.avg else 0,
    } for r in results]

    return render_template('reports/category.html', data=data)


@reports_bp.route('/export/csv')
@login_required
def export_csv():
    """Export all transactions as CSV."""
    transactions = Transaction.query.filter_by(
        user_id=current_user.user_id, is_deleted=False
    ).order_by(Transaction.transaction_date.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Type', 'Category', 'Amount', 'Description', 'Account'])

    for txn in transactions:
        cat_name = txn.category.name if txn.category else ''
        acct_name = txn.account.account_name if txn.account else ''
        writer.writerow([
            txn.transaction_date.isoformat(),
            txn.transaction_type,
            cat_name,
            str(txn.amount),
            txn.description or '',
            acct_name,
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=transactions_{date.today().isoformat()}.csv'}
    )


@reports_bp.route('/audit')
@login_required
def audit_log():
    """View audit log."""
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.filter_by(
        user_id=current_user.user_id
    ).order_by(AuditLog.changed_at.desc()).paginate(page=page, per_page=30, error_out=False)
    return render_template('reports/audit.html', logs=logs)
