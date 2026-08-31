from datetime import datetime
from ..extensions import db


class AuditLog(db.Model):
    """Audit log with user tracking and before/after diffs."""
    __tablename__ = 'audit_log'

    log_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    table_name = db.Column(db.String(100))
    operation = db.Column(db.String(50))
    record_id = db.Column(db.Integer)
    note = db.Column(db.String(255))
    old_value = db.Column(db.JSON)
    new_value = db.Column(db.JSON)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref='audit_logs')

    def __repr__(self):
        return f'<AuditLog {self.log_id}: {self.operation} on {self.table_name}>'
