from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func
from . import investments_bp
from .forms import InvestmentForm, SellForm
from ..extensions import db
from ..models.investment import Investment


@investments_bp.route('/')
@login_required
def index():
    investments = Investment.query.filter_by(user_id=current_user.user_id).order_by(
        Investment.sold_date.asc().nullsfirst(), Investment.purchase_date.desc()
    ).all()

    # Portfolio summary by asset type (active only)
    summary = db.session.query(
        Investment.asset_type,
        func.count(Investment.investment_id).label('count'),
        func.sum(Investment.purchase_amount).label('total_invested'),
        func.sum(Investment.current_value).label('total_value'),
    ).filter(
        Investment.user_id == current_user.user_id,
        Investment.sold_date.is_(None),
    ).group_by(Investment.asset_type).all()

    return render_template('investments/list.html', investments=investments, summary=summary)


@investments_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = InvestmentForm()
    if form.validate_on_submit():
        inv = Investment(
            user_id=current_user.user_id,
            asset_name=form.asset_name.data,
            asset_type=form.asset_type.data,
            purchase_amount=form.purchase_amount.data,
            current_value=form.current_value.data,
            purchase_date=form.purchase_date.data,
            currency=form.currency.data,
            notes=form.notes.data,
        )
        db.session.add(inv)
        db.session.commit()
        flash('Investment added!', 'success')
        return redirect(url_for('investments.index'))

    return render_template('investments/form.html', form=form, title='Add Investment')


@investments_bp.route('/edit/<int:inv_id>', methods=['GET', 'POST'])
@login_required
def edit(inv_id):
    inv = Investment.query.filter_by(
        investment_id=inv_id, user_id=current_user.user_id
    ).first_or_404()

    form = InvestmentForm(obj=inv)
    if form.validate_on_submit():
        inv.asset_name = form.asset_name.data
        inv.asset_type = form.asset_type.data
        inv.purchase_amount = form.purchase_amount.data
        inv.current_value = form.current_value.data
        inv.purchase_date = form.purchase_date.data
        inv.currency = form.currency.data
        inv.notes = form.notes.data
        db.session.commit()
        flash('Investment updated!', 'success')
        return redirect(url_for('investments.index'))

    return render_template('investments/form.html', form=form, title='Edit Investment')


@investments_bp.route('/sell/<int:inv_id>', methods=['GET', 'POST'])
@login_required
def sell(inv_id):
    inv = Investment.query.filter_by(
        investment_id=inv_id, user_id=current_user.user_id
    ).first_or_404()

    if inv.is_sold:
        flash('This investment has already been sold.', 'warning')
        return redirect(url_for('investments.index'))

    form = SellForm()
    if form.validate_on_submit():
        inv.sold_amount = form.sold_amount.data
        inv.sold_date = form.sold_date.data
        db.session.commit()
        flash(f'Investment sold! Realized gain/loss: {inv.realized_gain_loss:,.0f}', 'success')
        return redirect(url_for('investments.index'))

    return render_template('investments/sell.html', form=form, investment=inv)


@investments_bp.route('/delete/<int:inv_id>', methods=['POST'])
@login_required
def delete(inv_id):
    inv = Investment.query.filter_by(
        investment_id=inv_id, user_id=current_user.user_id
    ).first_or_404()
    db.session.delete(inv)
    db.session.commit()
    flash('Investment deleted.', 'info')
    return redirect(url_for('investments.index'))
