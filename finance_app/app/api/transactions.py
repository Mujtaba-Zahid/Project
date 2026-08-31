from flask import jsonify, request
from flask_login import login_required, current_user
from . import api_bp
from ..extensions import db
from ..models.transaction import Transaction


@api_bp.route('/transactions')
@login_required
def list_transactions():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    query = Transaction.query.filter_by(
        user_id=current_user.user_id, is_deleted=False
    )

    txn_type = request.args.get('type')
    if txn_type in ('income', 'expense'):
        query = query.filter_by(transaction_type=txn_type)

    pagination = query.order_by(Transaction.transaction_date.desc()).paginate(
        page=page, per_page=min(per_page, 100), error_out=False
    )

    return jsonify({
        'transactions': [{
            'id': t.transaction_id,
            'amount': str(t.amount),
            'type': t.transaction_type,
            'category_id': t.category_id,
            'account_id': t.account_id,
            'description': t.description,
            'date': t.transaction_date.isoformat(),
            'currency': t.currency,
        } for t in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
    })


@api_bp.route('/transactions', methods=['POST'])
@login_required
def create_transaction():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body required'}), 400

    required = ['account_id', 'amount', 'transaction_type', 'transaction_date']
    for field in required:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400

    from datetime import date as date_cls
    txn = Transaction(
        user_id=current_user.user_id,
        account_id=data['account_id'],
        category_id=data.get('category_id'),
        amount=data['amount'],
        transaction_type=data['transaction_type'],
        description=data.get('description', ''),
        transaction_date=date_cls.fromisoformat(data['transaction_date']),
        currency=data.get('currency', 'PKR'),
    )
    db.session.add(txn)
    db.session.commit()

    return jsonify({'id': txn.transaction_id, 'message': 'Created'}), 201


@api_bp.route('/transactions/<int:txn_id>', methods=['DELETE'])
@login_required
def delete_transaction(txn_id):
    txn = Transaction.query.filter_by(
        transaction_id=txn_id, user_id=current_user.user_id, is_deleted=False
    ).first()
    if not txn:
        return jsonify({'error': 'Not found'}), 404

    txn.soft_delete()
    db.session.commit()
    return jsonify({'message': 'Deleted'})
