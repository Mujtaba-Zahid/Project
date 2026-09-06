from datetime import datetime
from ..extensions import db


class Investment(db.Model):
    """Investment / fixed asset with sell tracking."""
    __tablename__ = 'investments'

    ASSET_TYPES = ('stock', 'gold', 'property', 'fixed_deposit', 'crypto', 'other')

    investment_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    asset_name = db.Column(db.String(100), nullable=False)
    asset_type = db.Column(db.String(30), nullable=False)
    purchase_amount = db.Column(db.Numeric(12, 2), nullable=False)
    current_value = db.Column(db.Numeric(12, 2), default=0)
    purchase_date = db.Column(db.Date, nullable=False)
    currency = db.Column(db.String(10), default='PKR')
    notes = db.Column(db.String(255))
    sold_date = db.Column(db.Date)
    sold_amount = db.Column(db.Numeric(12, 2))

    @property
    def gain_loss(self):
        """Unrealized gain/loss."""
        return float(self.current_value or 0) - float(self.purchase_amount)

    @property
    def gain_loss_pct(self):
        """Gain/loss as percentage."""
        if not self.purchase_amount or float(self.purchase_amount) == 0:
            return 0
        return round(self.gain_loss / float(self.purchase_amount) * 100, 2)

    @property
    def realized_gain_loss(self):
        """Realized gain/loss (only if sold)."""
        if self.sold_amount is None:
            return None
        return float(self.sold_amount) - float(self.purchase_amount)

    @property
    def realized_gain_loss_pct(self):
        """Realized gain/loss as percentage (only if sold)."""
        if self.sold_amount is None or not self.purchase_amount or float(self.purchase_amount) == 0:
            return None
        return round(self.realized_gain_loss / float(self.purchase_amount) * 100, 2)

    @property
    def is_sold(self):
        return self.sold_date is not None

    def __repr__(self):
        return f'<Investment {self.investment_id}: {self.asset_name}>'
