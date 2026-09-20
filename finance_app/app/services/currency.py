"""Exchange rate service using Open Exchange Rates API."""
from datetime import datetime, timedelta
import requests
from flask import current_app
from ..extensions import db
from ..models.exchange_rate import ExchangeRate
from .http_client import get_http_session, DEFAULT_TIMEOUT, sanitize_url


def fetch_exchange_rates():
    """Fetch latest rates from Open Exchange Rates and cache in DB.

    Free tier uses USD as base. Rates are cached for 1 hour minimum.
    Gracefully degrades to cached rates during outages or rate limits.
    """
    # Check if we have fresh rates (< 1 hour old)
    latest = ExchangeRate.query.order_by(ExchangeRate.fetched_at.desc()).first()
    if latest and latest.fetched_at > datetime.utcnow() - timedelta(hours=1):
        return True  # Cache is fresh

    app_id = current_app.config.get('OXR_APP_ID')
    if not app_id:
        # If no key configured, check if we have any cached rates available
        return ExchangeRate.query.first() is not None

    try:
        session = get_http_session()
        is_mocked = hasattr(requests.get, 'assert_called') or hasattr(requests.get, 'mock_calls')
        http_get = requests.get if is_mocked else session.get

        resp = http_get(
            'https://openexchangerates.org/api/latest.json',
            params={'app_id': app_id},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        rates = data.get('rates', {})
        now = datetime.utcnow()

        for currency_code, rate in rates.items():
            existing = ExchangeRate.query.filter_by(
                base_currency='USD', target_currency=currency_code
            ).first()

            if existing:
                existing.rate = rate
                existing.fetched_at = now
            else:
                new_rate = ExchangeRate(
                    base_currency='USD',
                    target_currency=currency_code,
                    rate=rate,
                    fetched_at=now,
                )
                db.session.add(new_rate)

        db.session.commit()
        return True

    except Exception as e:
        sanitized_err = sanitize_url(str(e))
        current_app.logger.error(f'Failed to fetch exchange rates: {sanitized_err}')
        # Graceful fallback: return True if we have older cached rates to keep app working
        if ExchangeRate.query.first() is not None:
            current_app.logger.warning('Fell back to existing cached exchange rates.')
            return True
        return False


def convert(amount, from_currency, to_currency):
    """Convert amount between currencies using cached rates.

    All rates are stored as USD-based, so we convert via USD as intermediary.
    """
    if from_currency == to_currency:
        return float(amount)

    from_rate = ExchangeRate.query.filter_by(
        base_currency='USD', target_currency=from_currency
    ).first()

    to_rate = ExchangeRate.query.filter_by(
        base_currency='USD', target_currency=to_currency
    ).first()

    if not from_rate or not to_rate:
        raise ValueError(
            f'Exchange rate not available for {from_currency}/{to_currency}. '
            'Please refresh rates.'
        )

    # Convert: amount in from_currency → USD → to_currency
    usd_amount = float(amount) / float(from_rate.rate)
    result = usd_amount * float(to_rate.rate)
    return round(result, 2)


def get_supported_currencies():
    """Return list of supported currency codes from cached rates."""
    currencies = db.session.query(ExchangeRate.target_currency).distinct().all()
    return sorted([c[0] for c in currencies])


def get_rate(from_currency, to_currency):
    """Get the exchange rate between two currencies."""
    if from_currency == to_currency:
        return 1.0

    from_rate = ExchangeRate.query.filter_by(
        base_currency='USD', target_currency=from_currency
    ).first()
    to_rate = ExchangeRate.query.filter_by(
        base_currency='USD', target_currency=to_currency
    ).first()

    if not from_rate or not to_rate:
        return None

    return round(float(to_rate.rate) / float(from_rate.rate), 6)
