from flask_wtf import FlaskForm
from wtforms import (StringField, DecimalField, SelectField, DateField,
                     TextAreaField, SubmitField, SelectMultipleField)
from wtforms.validators import DataRequired, NumberRange, Optional


class TransactionForm(FlaskForm):
    """Form for creating/editing a transaction."""
    account_id = SelectField('Account', coerce=int, validators=[DataRequired()])
    category_id = SelectField('Category', coerce=int, validators=[DataRequired()])
    amount = DecimalField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    transaction_type = SelectField('Type', choices=[
        ('income', 'Income'), ('expense', 'Expense')
    ], validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    transaction_date = DateField('Date', validators=[DataRequired()])
    tag_ids = SelectMultipleField('Tags', coerce=int, validators=[Optional()])
    submit = SubmitField('Save Transaction')


class TransferForm(FlaskForm):
    """Form for fund transfers between accounts."""
    from_account_id = SelectField('From Account', coerce=int, validators=[DataRequired()])
    to_account_id = SelectField('To Account', coerce=int, validators=[DataRequired()])
    amount = DecimalField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Transfer')
