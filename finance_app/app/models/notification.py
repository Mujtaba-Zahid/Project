from datetime import datetime
from ..extensions import db


class Notification(db.Model):
    """In-app notification with read tracking."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 'budget_alert', 'recurring_due', 'goal_completed'
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Notification {self.id}: {self.type}>'
