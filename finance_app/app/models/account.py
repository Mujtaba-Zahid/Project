from datetime import datetime
from ..extensions import db


class Account(db.Model):
    """User wallet / bank account with soft delete."""
    __tablename__ = 'accounts'

    ACCOUNT_TYPES = ('cash', 'bank', 'credit', 'wallet')

    account_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    account_name = db.Column(db.String(100), nullable=False)
    account_type = db.Column(db.String(20), nullable=False)
    currency = db.Column(db.String(10), default='PKR')
    is_active = db.Column(db.Boolean, default=True)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    transactions = db.relationship('Transaction', backref='account', lazy='dynamic')

    @property
    def balance(self):
        """Compute live balance from transactions."""
        from .transaction import Transaction
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
            Transaction.account_id == self.account_id,
            Transaction.is_deleted == False
        ).scalar()
        return result

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.is_active = False

    def __repr__(self):
        return f'<Account {self.account_id}: {self.account_name}>'
