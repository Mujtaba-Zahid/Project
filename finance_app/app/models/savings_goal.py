from datetime import datetime, date
from ..extensions import db


class SavingsGoal(db.Model):
    """Savings goal with progress tracking and soft delete."""
    __tablename__ = 'savings_goals'

    STATUSES = ('active', 'completed', 'cancelled')

    goal_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    goal_name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Numeric(12, 2), nullable=False)
    saved_amount = db.Column(db.Numeric(12, 2), default=0)
    deadline = db.Column(db.Date)
    status = db.Column(db.String(20), default='active')
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime)

    # Relationships
    contributions = db.relationship('SavingsContribution', backref='goal', lazy='dynamic',
                                     order_by='SavingsContribution.contributed_at.desc()')

    @property
    def progress_pct(self):
        """Percentage of goal completed."""
        if not self.target_amount or float(self.target_amount) == 0:
            return 0
        return round(float(self.saved_amount) / float(self.target_amount) * 100, 2)

    @property
    def remaining(self):
        return max(float(self.target_amount) - float(self.saved_amount), 0)

    @property
    def is_overdue(self):
        return self.deadline and self.deadline < date.today() and self.status == 'active'

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.status = 'cancelled'

    def __repr__(self):
        return f'<SavingsGoal {self.goal_id}: {self.goal_name}>'


class SavingsContribution(db.Model):
    """Individual contribution to a savings goal."""
    __tablename__ = 'savings_contributions'

    contribution_id = db.Column(db.Integer, primary_key=True)
    goal_id = db.Column(db.Integer, db.ForeignKey('savings_goals.goal_id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.String(255))
    contributed_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    account = db.relationship('Account', backref='savings_contributions')

    def __repr__(self):
        return f'<SavingsContribution {self.contribution_id}: {self.amount} to goal {self.goal_id}>'
