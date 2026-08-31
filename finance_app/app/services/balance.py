"""Balance, deposit, and withdrawal services — replaces SQL stored procedures."""
from datetime import date
from ..extensions import db
from ..models.transaction import Transaction
from ..models.account import Account
from .audit import log_action


def get_balance(account_id):
    """Get live balance for an account (replaces get_balance SQL function)."""
    result = db.session.query(
        db.func.coalesce(
            db.func.sum(
                db.case(
                    (Transaction.transaction_type == 'income', Transaction.amount),
                    else_=-Transaction.amount
                )
            ), 0
        )
    ).filter(
        Transaction.account_id == account_id,
        Transaction.is_deleted == False  # noqa: E712
    ).scalar()
    return float(result)


def deposit(account_id, amount, description='Manual Deposit', user_id=None, category_id=None):
    """Deposit into account (replaces deposit_amount procedure)."""
    account = db.session.get(Account, account_id)
    if not account or account.is_deleted:
        raise ValueError(f'Account {account_id} not found or deleted.')
    if not account.is_active:
        raise ValueError(f'Account {account_id} is inactive.')
    if amount <= 0:
        raise ValueError('Amount must be positive.')

    uid = user_id or account.user_id
    txn = Transaction(
        user_id=uid,
        account_id=account_id,
        category_id=category_id,
        amount=amount,
        transaction_type='income',
        transaction_date=date.today(),
        description=description,
        currency=account.currency,
    )
    db.session.add(txn)
    log_action('transactions', 'deposit', account_id, uid, note=f'deposited {amount}')
    db.session.commit()
    return txn


def withdraw(account_id, amount, description='Manual Withdrawal', user_id=None, category_id=None):
    """Withdraw with balance check (replaces withdraw_amount procedure)."""
    account = db.session.get(Account, account_id)
    if not account or account.is_deleted:
        raise ValueError(f'Account {account_id} not found or deleted.')
    if not account.is_active:
        raise ValueError(f'Account {account_id} is inactive.')
    if amount <= 0:
        raise ValueError('Amount must be positive.')

    current_balance = get_balance(account_id)
    if current_balance < amount:
        raise ValueError(
            f'Insufficient balance in account {account_id}. '
            f'Available: {current_balance}, requested: {amount}'
        )

    uid = user_id or account.user_id
    txn = Transaction(
        user_id=uid,
        account_id=account_id,
        category_id=category_id,
        amount=amount,
        transaction_type='expense',
        transaction_date=date.today(),
        description=description,
        currency=account.currency,
    )
    db.session.add(txn)
    log_action('transactions', 'withdrawal', account_id, uid, note=f'withdrew {amount}')
    db.session.commit()
    return txn
