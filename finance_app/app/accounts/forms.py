from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length


class AccountForm(FlaskForm):
    """Form for creating/editing an account."""
    account_name = StringField('Account Name', validators=[DataRequired(), Length(max=100)])
    account_type = SelectField('Account Type', choices=[
        ('cash', 'Cash'), ('bank', 'Bank'), ('credit', 'Credit Card'), ('wallet', 'Wallet')
    ], validators=[DataRequired()])
    currency = StringField('Currency', validators=[DataRequired(), Length(max=10)], default='PKR')
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Account')
