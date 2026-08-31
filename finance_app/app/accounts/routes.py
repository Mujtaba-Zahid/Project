from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from . import accounts_bp
from .forms import AccountForm
from ..extensions import db
from ..models.account import Account
from ..models.transaction import Transaction
from ..services.audit import log_action


@accounts_bp.route('/')
@login_required
def index():
    accounts = Account.query.filter_by(
        user_id=current_user.user_id, is_deleted=False
    ).all()
    return render_template('accounts/list.html', accounts=accounts)


@accounts_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = AccountForm()
    if form.validate_on_submit():
        account = Account(
            user_id=current_user.user_id,
            account_name=form.account_name.data,
            account_type=form.account_type.data,
            currency=form.currency.data,
            is_active=form.is_active.data,
        )
        db.session.add(account)
        db.session.flush()
        log_action('accounts', 'create', account.account_id, current_user.user_id,
                   note=f'created {account.account_name}')
        db.session.commit()
        flash('Account created!', 'success')
        return redirect(url_for('accounts.index'))

    return render_template('accounts/form.html', form=form, title='Add Account')


@accounts_bp.route('/edit/<int:account_id>', methods=['GET', 'POST'])
@login_required
def edit(account_id):
    account = Account.query.filter_by(
        account_id=account_id, user_id=current_user.user_id, is_deleted=False
    ).first_or_404()

    form = AccountForm(obj=account)
    if form.validate_on_submit():
        account.account_name = form.account_name.data
        account.account_type = form.account_type.data
        account.currency = form.currency.data
        account.is_active = form.is_active.data
        log_action('accounts', 'update', account.account_id, current_user.user_id,
                   note=f'updated {account.account_name}')
        db.session.commit()
        flash('Account updated!', 'success')
        return redirect(url_for('accounts.index'))

    return render_template('accounts/form.html', form=form, title='Edit Account')


@accounts_bp.route('/delete/<int:account_id>', methods=['POST'])
@login_required
def delete(account_id):
    account = Account.query.filter_by(
        account_id=account_id, user_id=current_user.user_id, is_deleted=False
    ).first_or_404()

    account.soft_delete()
    log_action('accounts', 'delete', account.account_id, current_user.user_id,
               note=f'deleted {account.account_name}')
    db.session.commit()
    flash('Account deleted.', 'info')
    return redirect(url_for('accounts.index'))


@accounts_bp.route('/<int:account_id>')
@login_required
def detail(account_id):
    account = Account.query.filter_by(
        account_id=account_id, user_id=current_user.user_id, is_deleted=False
    ).first_or_404()

    page = request.args.get('page', 1, type=int)
    transactions = Transaction.query.filter_by(
        account_id=account_id, is_deleted=False
    ).order_by(Transaction.transaction_date.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    return render_template('accounts/detail.html',
                           account=account, transactions=transactions)
