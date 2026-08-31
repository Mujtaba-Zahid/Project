"""Savings goal service — replaces SQL functions/procedures."""
from datetime import datetime
from ..extensions import db
from ..models.savings_goal import SavingsGoal, SavingsContribution
from ..models.account import Account
from .balance import get_balance
from .audit import log_action
from .notifications import create_notification


def get_goal_progress(goal_id):
    """Get savings goal progress percentage (replaces get_goal_progress SQL function)."""
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal:
        return 0
    return goal.progress_pct


def contribute_to_goal(goal_id, amount, account_id=None, user_id=None, note=None):
    """Add a contribution to a savings goal, optionally from an account."""
    goal = db.session.get(SavingsGoal, goal_id)
    if not goal or goal.is_deleted:
        raise ValueError(f'Savings goal {goal_id} not found.')
    if goal.status != 'active':
        raise ValueError(f'Savings goal is {goal.status}, not active.')
    if amount <= 0:
        raise ValueError('Contribution amount must be positive.')

    # If contributing from an account, check balance
    if account_id:
        account = db.session.get(Account, account_id)
        if not account or account.is_deleted or not account.is_active:
            raise ValueError(f'Account {account_id} not available.')
        balance = get_balance(account_id)
        if balance < amount:
            raise ValueError(f'Insufficient balance. Available: {balance}')

    # Record contribution
    contribution = SavingsContribution(
        goal_id=goal_id,
        account_id=account_id,
        amount=amount,
        note=note or f'Contribution of {amount}',
        contributed_at=datetime.utcnow(),
    )
    db.session.add(contribution)

    # Update saved amount
    goal.saved_amount = float(goal.saved_amount or 0) + amount
    db.session.add(goal)

    log_action('savings_goals', 'contribution', goal_id, user_id or goal.user_id,
               note=f'contributed {amount} to {goal.goal_name}')

    # Auto-complete if target reached
    if float(goal.saved_amount) >= float(goal.target_amount):
        goal.status = 'completed'
        create_notification(
            user_id=goal.user_id,
            notif_type='goal_completed',
            title=f'🎉 Goal Reached: {goal.goal_name}',
            message=f'Congratulations! You have saved {goal.saved_amount} '
                    f'and reached your target of {goal.target_amount}.',
        )

    db.session.commit()
    return contribution
