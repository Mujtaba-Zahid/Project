from datetime import date
from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from . import budgets_bp
from .forms import BudgetForm
from ..extensions import db
from ..models.budget import Budget
from ..models.category import Category
from ..services.budget import get_budget_status


@budgets_bp.route('/')
@login_required
def index():
    month_start = date.today().replace(day=1)
    budget_status = get_budget_status(current_user.user_id, month_start)
    return render_template('budgets/list.html', budget_status=budget_status,
                           current_month=month_start)


@budgets_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = BudgetForm()
    categories = Category.query.filter(
        db.or_(Category.user_id == current_user.user_id, Category.user_id.is_(None)),
        Category.type == 'expense'
    ).all()
    form.category_id.choices = [(c.category_id, f'{c.icon} {c.name}') for c in categories]

    if form.validate_on_submit():
        budget = Budget(
            user_id=current_user.user_id,
            category_id=form.category_id.data,
            monthly_limit=form.monthly_limit.data,
            month=form.month.data.replace(day=1),
        )
        db.session.add(budget)
        db.session.commit()
        flash('Budget created!', 'success')
        return redirect(url_for('budgets.index'))

    form.month.data = form.month.data or date.today().replace(day=1)
    return render_template('budgets/form.html', form=form, title='Add Budget')


@budgets_bp.route('/edit/<int:budget_id>', methods=['GET', 'POST'])
@login_required
def edit(budget_id):
    budget = Budget.query.filter_by(
        budget_id=budget_id, user_id=current_user.user_id
    ).first_or_404()

    form = BudgetForm(obj=budget)
    categories = Category.query.filter(
        db.or_(Category.user_id == current_user.user_id, Category.user_id.is_(None)),
        Category.type == 'expense'
    ).all()
    form.category_id.choices = [(c.category_id, f'{c.icon} {c.name}') for c in categories]

    if form.validate_on_submit():
        budget.category_id = form.category_id.data
        budget.monthly_limit = form.monthly_limit.data
        budget.month = form.month.data.replace(day=1)
        budget.alert_sent = False  # Reset alert on limit change
        db.session.commit()
        flash('Budget updated!', 'success')
        return redirect(url_for('budgets.index'))

    return render_template('budgets/form.html', form=form, title='Edit Budget')


@budgets_bp.route('/delete/<int:budget_id>', methods=['POST'])
@login_required
def delete(budget_id):
    budget = Budget.query.filter_by(
        budget_id=budget_id, user_id=current_user.user_id
    ).first_or_404()
    db.session.delete(budget)
    db.session.commit()
    flash('Budget deleted.', 'info')
    return redirect(url_for('budgets.index'))
