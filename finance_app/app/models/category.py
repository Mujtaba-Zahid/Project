from ..extensions import db


class Category(db.Model):
    """Income/expense category — user-specific or global default."""
    __tablename__ = 'categories'

    CATEGORY_TYPES = ('income', 'expense')

    category_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    icon = db.Column(db.String(50), default='📁')
    is_default = db.Column(db.Boolean, default=False)

    # Relationships
    transactions = db.relationship('Transaction', backref='category', lazy='dynamic')
    budgets = db.relationship('Budget', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<Category {self.category_id}: {self.name} ({self.type})>'
