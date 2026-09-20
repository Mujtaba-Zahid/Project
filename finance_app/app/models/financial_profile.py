"""Financial health profile — Kaggle-calibrated metrics for the AI advisor."""
from datetime import datetime
from typing import Optional
from ..extensions import db
from ..services.crypto import encrypt_credential, decrypt_credential


class FinancialProfile(db.Model):
    """Stores user's financial health indicators used by the AI advisor.

    15 Kaggle-calibrated metrics powering the financial health score,
    LLM context injection, and personalized recommendation weighting.
    """
    __tablename__ = 'financial_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.user_id'),
        nullable=False, unique=True
    )

    # --- Core financial metrics ---
    monthly_income_pkr = db.Column(db.Float, default=80000.0)
    income_type = db.Column(db.String(50), default='Salary')  # Salary, Business, Freelance, etc.
    credit_score = db.Column(db.Integer, default=680)
    debt_to_income_ratio = db.Column(db.Float, default=0.35)
    savings_rate = db.Column(db.Float, default=0.12)

    # --- Status indicators ---
    financial_stress_level = db.Column(db.String(20), default='Medium')  # Low, Medium, High
    cash_flow_status = db.Column(db.String(20), default='Neutral')      # Positive, Neutral, Negative
    financial_scenario = db.Column(db.String(30), default='normal')     # normal, high_inflation, emergency

    # --- Fund & liability tracking ---
    emergency_fund_pkr = db.Column(db.Float, default=0.0)
    emergency_fund_months = db.Column(db.Float, default=1.0)
    loan_payment_pkr = db.Column(db.Float, default=0.0)
    investment_amount_pkr = db.Column(db.Float, default=0.0)

    # --- Goals & habits ---
    subscription_services = db.Column(db.Integer, default=3)
    savings_goal_met = db.Column(db.Boolean, default=False)

    # --- Computed score (0–100 composite) ---
    financial_advice_score = db.Column(db.Integer, default=50)

    # --- AI / Groq LLM Configuration (Encrypted at rest) ---
    _groq_api_key = db.Column('groq_api_key', db.String(255), nullable=True)
    preferred_model = db.Column(db.String(100), default='llama-3.3-70b-versatile')

    @property
    def groq_api_key(self) -> Optional[str]:
        """Decrypt and return user's custom Groq API key."""
        if not self._groq_api_key:
            return None
        return decrypt_credential(self._groq_api_key)

    @groq_api_key.setter
    def groq_api_key(self, value: Optional[str]):
        """Encrypt and store user's custom Groq API key."""
        if not value or not str(value).strip():
            self._groq_api_key = None
        else:
            self._groq_api_key = encrypt_credential(str(value).strip())

    @property
    def raw_encrypted_key(self) -> Optional[str]:
        """Return the raw ciphertext stored in the database for auditing."""
        return self._groq_api_key

    # --- Metadata ---
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def compute_score(self):
        """Calculate composite financial health score (0–100).

        Weights:
          - Credit score contribution     : 25%
          - Savings rate                   : 20%
          - DTI ratio                      : 20%
          - Emergency fund adequacy        : 15%
          - Cash flow direction            : 10%
          - Savings goal achievement       : 10%
        """
        score = 0.0

        # Credit score (300–850 → 0–25)
        cs = max(300, min(self.credit_score or 680, 850))
        score += ((cs - 300) / 550) * 25

        # Savings rate (0%–30%+ → 0–20)
        sr = max(0, min(self.savings_rate or 0, 0.30))
        score += (sr / 0.30) * 20

        # DTI ratio (inverse — lower is better, 0–0.60 → 20–0)
        dti = max(0, min(self.debt_to_income_ratio or 0, 0.60))
        score += (1 - dti / 0.60) * 20

        # Emergency fund months (0–6+ → 0–15)
        ef = max(0, min(self.emergency_fund_months or 0, 6))
        score += (ef / 6) * 15

        # Cash flow direction
        cf_map = {'Positive': 10, 'Neutral': 5, 'Negative': 0}
        score += cf_map.get(self.cash_flow_status, 5)

        # Savings goal
        score += 10 if self.savings_goal_met else 0

        self.financial_advice_score = int(round(score))
        return self.financial_advice_score

    @property
    def has_custom_api_key(self) -> bool:
        return bool(self.groq_api_key and self.groq_api_key.strip())

    @property
    def masked_api_key(self) -> str:
        if not self.has_custom_api_key:
            return ""
        key = self.groq_api_key.strip()
        if len(key) <= 8:
            return "••••••••"
        return key[:4] + "••••••••" + key[-4:]

    def to_dict(self):
        """Serialize for LLM context building."""
        return {
            'monthly_income_pkr': self.monthly_income_pkr,
            'income_type': self.income_type,
            'credit_score': self.credit_score,
            'debt_to_income_ratio': self.debt_to_income_ratio,
            'savings_rate': self.savings_rate,
            'financial_stress_level': self.financial_stress_level,
            'cash_flow_status': self.cash_flow_status,
            'financial_scenario': self.financial_scenario,
            'emergency_fund_pkr': self.emergency_fund_pkr,
            'emergency_fund_months': self.emergency_fund_months,
            'loan_payment_pkr': self.loan_payment_pkr,
            'investment_amount_pkr': self.investment_amount_pkr,
            'subscription_services': self.subscription_services,
            'savings_goal_met': self.savings_goal_met,
            'financial_advice_score': self.financial_advice_score,
            'has_custom_api_key': self.has_custom_api_key,
            'preferred_model': self.preferred_model or 'llama-3.3-70b-versatile',
        }

    def __repr__(self):
        return f'<FinancialProfile user={self.user_id} score={self.financial_advice_score}>'
