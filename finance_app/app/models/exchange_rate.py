from datetime import datetime
from ..extensions import db


class ExchangeRate(db.Model):
    """Cached exchange rate from Open Exchange Rates."""
    __tablename__ = 'exchange_rates'

    id = db.Column(db.Integer, primary_key=True)
    base_currency = db.Column(db.String(10), nullable=False, default='USD')
    target_currency = db.Column(db.String(10), nullable=False)
    rate = db.Column(db.Numeric(16, 8), nullable=False)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('base_currency', 'target_currency', name='uq_currency_pair'),
    )

    def __repr__(self):
        return f'<ExchangeRate {self.base_currency}/{self.target_currency}: {self.rate}>'
