from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from . import savings_bp
from .forms import SavingsGoalForm, ContributionForm
from ..extensions import db
from ..models.savings_goal import SavingsGoal
from ..models.account import Account
from ..services.savings import contribute_to_goal


@savings_bp.route('/')
@login_required
def index():
    goals = SavingsGoal.query.filter_by(
        user_id=current_user.user_id, is_deleted=False
    ).order_by(SavingsGoal.status.asc(), SavingsGoal.deadline.asc()).all()
    return render_template('savings/list.html', goals=goals)


@savings_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = SavingsGoalForm()
    if form.validate_on_submit():
        goal = SavingsGoal(
            user_id=current_user.user_id,
            goal_name=form.goal_name.data,
            target_amount=form.target_amount.data,
            deadline=form.deadline.data,
        )
        db.session.add(goal)
        db.session.commit()
        flash('Savings goal created!', 'success')
        return redirect(url_for('savings.index'))

    return render_template('savings/form.html', form=form, title='Add Savings Goal')


@savings_bp.route('/edit/<int:goal_id>', methods=['GET', 'POST'])
@login_required
def edit(goal_id):
    goal = SavingsGoal.query.filter_by(
        goal_id=goal_id, user_id=current_user.user_id, is_deleted=False
    ).first_or_404()

    form = SavingsGoalForm(obj=goal)
    if form.validate_on_submit():
        goal.goal_name = form.goal_name.data
        goal.target_amount = form.target_amount.data
        goal.deadline = form.deadline.data
        db.session.commit()
        flash('Goal updated!', 'success')
        return redirect(url_for('savings.index'))

    return render_template('savings/form.html', form=form, title='Edit Goal')


@savings_bp.route('/contribute/<int:goal_id>', methods=['GET', 'POST'])
@login_required
def contribute(goal_id):
    goal = SavingsGoal.query.filter_by(
        goal_id=goal_id, user_id=current_user.user_id, is_deleted=False
    ).first_or_404()

    form = ContributionForm()
    accounts = Account.query.filter_by(
        user_id=current_user.user_id, is_deleted=False, is_active=True
    ).all()
    form.account_id.choices = [(0, '-- No account deduction --')] + [
        (a.account_id, f'{a.account_name} ({a.currency})') for a in accounts
    ]

    if form.validate_on_submit():
        try:
            acct_id = form.account_id.data if form.account_id.data != 0 else None
            contribute_to_goal(
                goal_id=goal_id,
                amount=float(form.amount.data),
                account_id=acct_id,
                user_id=current_user.user_id,
                note=form.note.data,
            )
            flash('Contribution added!', 'success')
            return redirect(url_for('savings.index'))
        except ValueError as e:
            flash(str(e), 'danger')

    return render_template('savings/contribute.html', form=form, goal=goal)


@savings_bp.route('/delete/<int:goal_id>', methods=['POST'])
@login_required
def delete(goal_id):
    goal = SavingsGoal.query.filter_by(
        goal_id=goal_id, user_id=current_user.user_id, is_deleted=False
    ).first_or_404()
    goal.soft_delete()
    db.session.commit()
    flash('Goal cancelled.', 'info')
    return redirect(url_for('savings.index'))
