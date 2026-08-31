from ..extensions import db


class Budget(db.Model):
    """Monthly category budget with alert tracking."""
    __tablename__ = 'budgets'

    budget_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.category_id'), nullable=False)
    monthly_limit = db.Column(db.Numeric(12, 2), nullable=False)
    month = db.Column(db.Date, nullable=False)
    alert_threshold = db.Column(db.Numeric(3, 2), default=0.80)
    alert_sent = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Budget {self.budget_id}: {self.monthly_limit} for category {self.category_id}>'
