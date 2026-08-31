from datetime import date, timedelta
from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from . import recurring_bp
from .forms import RecurringForm
from ..extensions import db
from ..models.recurring import RecurringTransaction
from ..models.transaction import Transaction
from ..models.account import Account
from ..models.category import Category
from ..services.audit import log_action


@recurring_bp.route('/')
@login_required
def index():
    items = RecurringTransaction.query.filter_by(
        user_id=current_user.user_id
    ).order_by(RecurringTransaction.next_due_date.asc()).all()
    return render_template('recurring/list.html', items=items, today=date.today())


@recurring_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = RecurringForm()
    _populate_choices(form)

    if form.validate_on_submit():
        item = RecurringTransaction(
            user_id=current_user.user_id,
            account_id=form.account_id.data,
            category_id=form.category_id.data,
            amount=form.amount.data,
            transaction_type=form.transaction_type.data,
            frequency=form.frequency.data,
            next_due_date=form.next_due_date.data,
            description=form.description.data,
        )
        db.session.add(item)
        db.session.commit()
        flash('Recurring transaction created!', 'success')
        return redirect(url_for('recurring.index'))

    return render_template('recurring/form.html', form=form, title='Add Recurring Transaction')


@recurring_bp.route('/edit/<int:rec_id>', methods=['GET', 'POST'])
@login_required
def edit(rec_id):
    item = RecurringTransaction.query.filter_by(
        recurring_id=rec_id, user_id=current_user.user_id
    ).first_or_404()

    form = RecurringForm(obj=item)
    _populate_choices(form)

    if form.validate_on_submit():
        item.account_id = form.account_id.data
        item.category_id = form.category_id.data
        item.amount = form.amount.data
        item.transaction_type = form.transaction_type.data
        item.frequency = form.frequency.data
        item.next_due_date = form.next_due_date.data
        item.description = form.description.data
        db.session.commit()
        flash('Recurring transaction updated!', 'success')
        return redirect(url_for('recurring.index'))

    return render_template('recurring/form.html', form=form, title='Edit Recurring Transaction')


@recurring_bp.route('/toggle/<int:rec_id>', methods=['POST'])
@login_required
def toggle(rec_id):
    item = RecurringTransaction.query.filter_by(
        recurring_id=rec_id, user_id=current_user.user_id
    ).first_or_404()
    item.is_active = not item.is_active
    db.session.commit()
    status = 'activated' if item.is_active else 'paused'
    flash(f'Recurring transaction {status}.', 'info')
    return redirect(url_for('recurring.index'))


@recurring_bp.route('/process', methods=['POST'])
@login_required
def process_due():
    """Process all due recurring transactions — create actual transactions."""
    today = date.today()
    due_items = RecurringTransaction.query.filter(
        RecurringTransaction.user_id == current_user.user_id,
        RecurringTransaction.is_active == True,
        RecurringTransaction.next_due_date <= today,
    ).all()

    count = 0
    for item in due_items:
        txn = Transaction(
            user_id=current_user.user_id,
            account_id=item.account_id,
            category_id=item.category_id,
            amount=item.amount,
            transaction_type=item.transaction_type,
            transaction_date=today,
            description=f'[Auto] {item.description}',
        )
        db.session.add(txn)

        # Advance next due date
        item.last_processed_date = today
        if item.frequency == 'daily':
            item.next_due_date = today + timedelta(days=1)
        elif item.frequency == 'weekly':
            item.next_due_date = today + timedelta(weeks=1)
        elif item.frequency == 'monthly':
            month = today.month + 1 if today.month < 12 else 1
            year = today.year if today.month < 12 else today.year + 1
            item.next_due_date = today.replace(year=year, month=month)
        elif item.frequency == 'yearly':
            item.next_due_date = today.replace(year=today.year + 1)

        count += 1

    db.session.commit()
    flash(f'Processed {count} recurring transaction(s).', 'success')
    return redirect(url_for('recurring.index'))


@recurring_bp.route('/delete/<int:rec_id>', methods=['POST'])
@login_required
def delete(rec_id):
    item = RecurringTransaction.query.filter_by(
        recurring_id=rec_id, user_id=current_user.user_id
    ).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash('Recurring transaction deleted.', 'info')
    return redirect(url_for('recurring.index'))


def _populate_choices(form):
    accounts = Account.query.filter_by(
        user_id=current_user.user_id, is_deleted=False, is_active=True
    ).all()
    form.account_id.choices = [(a.account_id, a.account_name) for a in accounts]

    categories = Category.query.filter(
        db.or_(Category.user_id == current_user.user_id, Category.user_id.is_(None))
    ).all()
    form.category_id.choices = [(c.category_id, f'{c.icon} {c.name}') for c in categories]
