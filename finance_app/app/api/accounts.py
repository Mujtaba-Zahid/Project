from flask import jsonify
from flask_login import login_required, current_user
from . import api_bp
from ..models.account import Account
from ..services.balance import get_balance


@api_bp.route('/accounts')
@login_required
def list_accounts():
    accounts = Account.query.filter_by(
        user_id=current_user.user_id, is_deleted=False
    ).all()

    return jsonify({
        'accounts': [{
            'id': a.account_id,
            'name': a.account_name,
            'type': a.account_type,
            'currency': a.currency,
            'balance': get_balance(a.account_id),
            'is_active': a.is_active,
        } for a in accounts]
    })


@api_bp.route('/accounts/<int:account_id>/balance')
@login_required
def account_balance(account_id):
    account = Account.query.filter_by(
        account_id=account_id, user_id=current_user.user_id, is_deleted=False
    ).first()
    if not account:
        return jsonify({'error': 'Not found'}), 404

    return jsonify({
        'account_id': account.account_id,
        'name': account.account_name,
        'balance': get_balance(account.account_id),
        'currency': account.currency,
    })
