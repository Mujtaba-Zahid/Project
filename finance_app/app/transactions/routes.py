from datetime import date, datetime
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import transactions_bp
from .forms import TransactionForm, TransferForm
from ..extensions import db
from ..models.transaction import Transaction, TransactionTag
from ..models.account import Account
from ..models.category import Category
from ..models.tag import Tag
from ..services.transfer import fund_transfer
from ..services.budget import check_and_alert
from ..services.audit import log_action


@transactions_bp.route('/')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = Transaction.query.filter_by(
        user_id=current_user.user_id, is_deleted=False
    )

    # Filters
    txn_type = request.args.get('type')
    if txn_type in ('income', 'expense'):
        query = query.filter_by(transaction_type=txn_type)

    category_id = request.args.get('category_id', type=int)
    if category_id:
        query = query.filter_by(category_id=category_id)

    account_id = request.args.get('account_id', type=int)
    if account_id:
        query = query.filter_by(account_id=account_id)

    date_from = request.args.get('date_from')
    if date_from:
        query = query.filter(Transaction.transaction_date >= date_from)

    date_to = request.args.get('date_to')
    if date_to:
        query = query.filter(Transaction.transaction_date <= date_to)

    search = request.args.get('search', '').strip()
    if search:
        query = query.filter(Transaction.description.ilike(f'%{search}%'))

    pagination = query.order_by(Transaction.transaction_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    categories = Category.query.filter(
        db.or_(Category.user_id == current_user.user_id, Category.user_id.is_(None))
    ).all()
    accounts = Account.query.filter_by(
        user_id=current_user.user_id, is_deleted=False
    ).all()

    return render_template('transactions/list.html',
                           transactions=pagination.items,
                           pagination=pagination,
                           categories=categories,
                           accounts=accounts)


@transactions_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = TransactionForm()
    _populate_form_choices(form)

    if form.validate_on_submit():
        txn = Transaction(
            user_id=current_user.user_id,
            account_id=form.account_id.data,
            category_id=form.category_id.data,
            amount=form.amount.data,
            transaction_type=form.transaction_type.data,
            description=form.description.data,
            transaction_date=form.transaction_date.data,
        )
        db.session.add(txn)
        db.session.flush()

        # Add tags
        for tag_id in form.tag_ids.data:
            tt = TransactionTag(transaction_id=txn.transaction_id, tag_id=tag_id)
            db.session.add(tt)

        log_action('transactions', 'create', txn.transaction_id, current_user.user_id,
                   note=f'{txn.transaction_type} of {txn.amount}')

        db.session.commit()

        # Check budget alerts for expense transactions
        if txn.transaction_type == 'expense' and txn.category_id:
            check_and_alert(current_user.user_id, txn.category_id)

        flash('Transaction added!', 'success')
        return redirect(url_for('transactions.index'))

    form.transaction_date.data = form.transaction_date.data or date.today()
    return render_template('transactions/form.html', form=form, title='Add Transaction')


@transactions_bp.route('/edit/<int:txn_id>', methods=['GET', 'POST'])
@login_required
def edit(txn_id):
    txn = Transaction.query.filter_by(
        transaction_id=txn_id, user_id=current_user.user_id, is_deleted=False
    ).first_or_404()

    form = TransactionForm(obj=txn)
    _populate_form_choices(form)

    if form.validate_on_submit():
        old_values = {
            'amount': str(txn.amount),
            'type': txn.transaction_type,
            'category_id': txn.category_id,
        }

        txn.account_id = form.account_id.data
        txn.category_id = form.category_id.data
        txn.amount = form.amount.data
        txn.transaction_type = form.transaction_type.data
        txn.description = form.description.data
        txn.transaction_date = form.transaction_date.data

        # Update tags
        TransactionTag.query.filter_by(transaction_id=txn.transaction_id).delete()
        for tag_id in form.tag_ids.data:
            tt = TransactionTag(transaction_id=txn.transaction_id, tag_id=tag_id)
            db.session.add(tt)

        new_values = {
            'amount': str(txn.amount),
            'type': txn.transaction_type,
            'category_id': txn.category_id,
        }

        log_action('transactions', 'update', txn.transaction_id, current_user.user_id,
                   note='updated transaction', old_value=old_values, new_value=new_values)

        db.session.commit()
        flash('Transaction updated!', 'success')
        return redirect(url_for('transactions.index'))

    # Pre-select current tags
    form.tag_ids.data = [tt.tag_id for tt in
                          TransactionTag.query.filter_by(transaction_id=txn.transaction_id).all()]

    return render_template('transactions/form.html', form=form, title='Edit Transaction')


@transactions_bp.route('/delete/<int:txn_id>', methods=['POST'])
@login_required
def delete(txn_id):
    txn = Transaction.query.filter_by(
        transaction_id=txn_id, user_id=current_user.user_id, is_deleted=False
    ).first_or_404()

    txn.soft_delete()
    log_action('transactions', 'delete', txn.transaction_id, current_user.user_id,
               note=f'soft deleted {txn.transaction_type} of {txn.amount}')
    db.session.commit()

    flash('Transaction deleted.', 'info')
    return redirect(url_for('transactions.index'))


@transactions_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    form = TransferForm()
    accounts = Account.query.filter_by(
        user_id=current_user.user_id, is_deleted=False, is_active=True
    ).all()
    choices = [(a.account_id, f'{a.account_name} ({a.currency})') for a in accounts]
    form.from_account_id.choices = choices
    form.to_account_id.choices = choices

    if form.validate_on_submit():
        try:
            fund_transfer(
                from_account_id=form.from_account_id.data,
                to_account_id=form.to_account_id.data,
                amount=float(form.amount.data),
                user_id=current_user.user_id,
                notes=form.notes.data,
            )
            flash('Transfer completed!', 'success')
            return redirect(url_for('dashboard.index'))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('transactions/form.html', form=form, title='Fund Transfer',
                           is_transfer=True)


def _populate_form_choices(form):
    """Populate select field choices for transaction form."""
    accounts = Account.query.filter_by(
        user_id=current_user.user_id, is_deleted=False, is_active=True
    ).all()
    form.account_id.choices = [(a.account_id, a.account_name) for a in accounts]

    categories = Category.query.filter(
        db.or_(Category.user_id == current_user.user_id, Category.user_id.is_(None))
    ).all()
    form.category_id.choices = [(c.category_id, f'{c.icon} {c.name}') for c in categories]

    tags = Tag.query.filter(
        db.or_(Tag.user_id == current_user.user_id, Tag.user_id.is_(None))
    ).all()
    form.tag_ids.choices = [(t.tag_id, t.name) for t in tags]
