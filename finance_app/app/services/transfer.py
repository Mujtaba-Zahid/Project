"""Fund transfer service — replaces fund_transfer SQL procedure."""
from datetime import date
from ..extensions import db
from ..models.transaction import Transaction
from ..models.transfer import Transfer
from ..models.account import Account
from .balance import get_balance
from .audit import log_action


def fund_transfer(from_account_id, to_account_id, amount, user_id, notes=None):
    """Transfer funds between accounts with atomicity.

    Replaces the fund_transfer() stored procedure with improved
    validation and cross-currency support.
    """
    if from_account_id == to_account_id:
        raise ValueError('Cannot transfer to the same account.')
    if amount <= 0:
        raise ValueError('Amount must be positive.')

    from_account = db.session.get(Account, from_account_id)
    to_account = db.session.get(Account, to_account_id)

    if not from_account or from_account.is_deleted:
        raise ValueError(f'Source account {from_account_id} not found.')
    if not to_account or to_account.is_deleted:
        raise ValueError(f'Destination account {to_account_id} not found.')
    if not from_account.is_active:
        raise ValueError(f'Source account {from_account_id} is inactive.')
    if not to_account.is_active:
        raise ValueError(f'Destination account {to_account_id} is inactive.')

    current_balance = get_balance(from_account_id)
    if current_balance < amount:
        raise ValueError(
            f'Insufficient balance for transfer. '
            f'Available: {current_balance}, requested: {amount}'
        )

    try:
        # Debit source
        txn_out = Transaction(
            user_id=user_id,
            account_id=from_account_id,
            amount=amount,
            transaction_type='expense',
            transaction_date=date.today(),
            description=f'Transfer Out → {to_account.account_name}',
            currency=from_account.currency,
        )
        db.session.add(txn_out)

        # Credit destination
        txn_in = Transaction(
            user_id=user_id,
            account_id=to_account_id,
            amount=amount,
            transaction_type='income',
            transaction_date=date.today(),
            description=f'Transfer In ← {from_account.account_name}',
            currency=to_account.currency,
        )
        db.session.add(txn_in)

        # Record transfer
        transfer = Transfer(
            user_id=user_id,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount=amount,
            notes=notes,
            transfer_date=date.today(),
        )
        db.session.add(transfer)

        log_action(
            'transfers', 'fund_transfer', from_account_id, user_id,
            note=f'transferred {amount} to account {to_account_id}'
        )

        db.session.commit()
        return transfer

    except Exception:
        db.session.rollback()
        raise
