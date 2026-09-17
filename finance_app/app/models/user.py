from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from ..extensions import db


class User(UserMixin, db.Model):
    """User model with email/password and Google OAuth support."""
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256))
    google_id = db.Column(db.String(100), unique=True)
    avatar_url = db.Column(db.String(500))
    preferred_currency = db.Column(db.String(10), default='PKR')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    accounts = db.relationship('Account', backref='user', lazy='dynamic')
    transactions = db.relationship('Transaction', backref='user', lazy='dynamic')
    budgets = db.relationship('Budget', backref='user', lazy='dynamic')
    savings_goals = db.relationship('SavingsGoal', backref='user', lazy='dynamic')
    investments = db.relationship('Investment', backref='user', lazy='dynamic')
    recurring_transactions = db.relationship('RecurringTransaction', backref='user', lazy='dynamic')
    categories = db.relationship('Category', backref='user', lazy='dynamic')
    tags = db.relationship('Tag', backref='user', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')

    # AI Advisor relationships
    financial_profile = db.relationship('FinancialProfile', backref='user', uselist=False, lazy='joined')
    ai_messages = db.relationship('AiChatMessage', backref='user', lazy='dynamic', order_by='AiChatMessage.created_at')

    def get_id(self):
        return str(self.user_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def display_name(self):
        return self.name or self.email.split('@')[0]

    def __repr__(self):
        return f'<User {self.user_id}: {self.email}>'
