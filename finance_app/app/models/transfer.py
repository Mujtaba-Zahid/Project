from datetime import date
from ..extensions import db


class Transfer(db.Model):
    """Account-to-account fund transfer."""
    __tablename__ = 'transfers'

    transfer_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    from_account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    to_account_id = db.Column(db.Integer, db.ForeignKey('accounts.account_id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.String(255))
    transfer_date = db.Column(db.Date, default=date.today)

    # Relationships
    from_account = db.relationship('Account', foreign_keys=[from_account_id], backref='transfers_out')
    to_account = db.relationship('Account', foreign_keys=[to_account_id], backref='transfers_in')

    def __repr__(self):
        return f'<Transfer {self.transfer_id}: {self.amount} from {self.from_account_id} to {self.to_account_id}>'
