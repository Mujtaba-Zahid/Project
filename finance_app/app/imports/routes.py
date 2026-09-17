import os
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_required, current_user
from . import imports_bp
from .parser import parse_csv, clean_data
from ..extensions import db
from ..models.transaction import Transaction
from ..models.account import Account
from ..models.category import Category
from ..services.auto_categorizer import auto_categorize


@imports_bp.route('/', methods=['GET', 'POST'])
@login_required
def upload():
    accounts = Account.query.filter_by(
        user_id=current_user.user_id, is_deleted=False, is_active=True
    ).all()

    if request.method == 'POST':
        file = request.files.get('csv_file')
        account_id = request.form.get('account_id', type=int)

        if not file or not file.filename.endswith('.csv'):
            flash('Please upload a valid CSV file.', 'danger')
            return render_template('imports/upload.html', accounts=accounts)

        if not account_id:
            flash('Please select an account.', 'danger')
            return render_template('imports/upload.html', accounts=accounts)

        content = file.read()
        headers, rows = parse_csv(content)

        if not rows:
            flash('CSV file is empty.', 'danger')
            return render_template('imports/upload.html', accounts=accounts)

        # Store in session for preview
        session['import_headers'] = headers
        session['import_rows'] = rows[:100]  # Limit preview to 100 rows
        session['import_all_rows'] = rows
        session['import_account_id'] = account_id

        return render_template('imports/preview.html',
                               headers=headers, rows=rows[:20],
                               total_rows=len(rows), account_id=account_id)

    return render_template('imports/upload.html', accounts=accounts)


@imports_bp.route('/confirm', methods=['POST'])
@login_required
def confirm():
    """Process mapped and cleaned data into transactions."""
    rows = session.get('import_all_rows', [])
    account_id = session.get('import_account_id')

    if not rows or not account_id:
        flash('No data to import. Please upload again.', 'danger')
        return redirect(url_for('imports.upload'))

    # Get column mapping from form
    column_mapping = {
        'date': request.form.get('col_date', type=int),
        'amount': request.form.get('col_amount', type=int),
        'type': request.form.get('col_type', type=int),
        'description': request.form.get('col_description', type=int),
    }

    cleaned, errors = clean_data(rows, column_mapping)

    if not cleaned:
        flash(f'No valid rows to import. Errors: {len(errors)}', 'danger')
        return redirect(url_for('imports.upload'))

    # Build a category lookup for auto-categorization
    user_categories = {
        c.name: c.category_id
        for c in Category.query.filter(
            (Category.user_id == current_user.user_id) | (Category.is_default == True)
        ).all()
    }

    # Insert transactions with auto-categorization
    count = 0
    auto_categorized = 0
    for record in cleaned:
        category_id = None
        desc = record.get('description', '')

        # Try auto-categorization from description
        suggested_cat = auto_categorize(desc)
        if suggested_cat and suggested_cat in user_categories:
            category_id = user_categories[suggested_cat]
            auto_categorized += 1

        txn = Transaction(
            user_id=current_user.user_id,
            account_id=account_id,
            amount=record['amount'],
            transaction_type=record['type'],
            transaction_date=record['date'],
            description=record['description'],
            category_id=category_id,
        )
        db.session.add(txn)
        count += 1

    db.session.commit()

    # Clear session
    session.pop('import_headers', None)
    session.pop('import_rows', None)
    session.pop('import_all_rows', None)
    session.pop('import_account_id', None)

    msg = f'Successfully imported {count} transaction(s).'
    if auto_categorized:
        msg += f' Auto-categorized {auto_categorized} transaction(s) using AI.'
    if errors:
        msg += f' Skipped {len(errors)} row(s) with errors.'
    flash(msg, 'success')
    return redirect(url_for('transactions.index'))
