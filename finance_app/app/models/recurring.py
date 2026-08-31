from ..extensions import db


class RecurringTransaction(db.Model):
    """Scheduled / recurring payment with pause capability."""
    __tablename__ = 'recurring_transactions'

    FREQUENCIES = ('daily', 'weekly', 'monthly', 'yearly')

    recurring_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.category_id'))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    frequency = db.Column(db.String(20), nullable=False)
    next_due_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    last_processed_date = db.Column(db.Date)

    # Relationships
    account = db.relationship('Account', backref='recurring_transactions')
    category = db.relationship('Category', backref='recurring_transactions')

    def __repr__(self):
        return f'<RecurringTransaction {self.recurring_id}: {self.description}>'
