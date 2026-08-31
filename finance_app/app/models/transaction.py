from datetime import datetime
from ..extensions import db


class TransactionTag(db.Model):
    """Association table: transactions <-> tags."""
    __tablename__ = 'transaction_tags'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.transaction_id'), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.tag_id'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('transaction_id', 'tag_id', name='uq_transaction_tag'),
    )


class Transaction(db.Model):
    """Financial transaction with soft delete and multi-currency support."""
    __tablename__ = 'transactions'

    TRANSACTION_TYPES = ('income', 'expense')

    transaction_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.category_id'))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(255))
    transaction_date = db.Column(db.Date, nullable=False)
    currency = db.Column(db.String(10), default='PKR')
    exchange_rate = db.Column(db.Numeric(12, 6), default=1.0)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    tags = db.relationship('Tag', secondary='transaction_tags', backref='transactions', lazy='dynamic')

    # Indexes
    __table_args__ = (
        db.Index('idx_tx_date', 'transaction_date'),
        db.Index('idx_tx_amount', 'amount'),
        db.Index('idx_tx_category', 'category_id', 'transaction_type'),
        db.Index('idx_tx_user', 'user_id'),
        db.Index('idx_tx_account', 'account_id'),
    )

    @property
    def amount_in_base(self):
        """Amount converted to user's base currency."""
        return float(self.amount) * float(self.exchange_rate or 1)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()

    def __repr__(self):
        return f'<Transaction {self.transaction_id}: {self.transaction_type} {self.amount}>'
