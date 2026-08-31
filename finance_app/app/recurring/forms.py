from flask_wtf import FlaskForm
from wtforms import DecimalField, SelectField, DateField, StringField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional


class RecurringForm(FlaskForm):
    account_id = SelectField('Account', coerce=int, validators=[DataRequired()])
    category_id = SelectField('Category', coerce=int, validators=[DataRequired()])
    amount = DecimalField('Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    transaction_type = SelectField('Type', choices=[
        ('income', 'Income'), ('expense', 'Expense')
    ], validators=[DataRequired()])
    frequency = SelectField('Frequency', choices=[
        ('daily', 'Daily'), ('weekly', 'Weekly'),
        ('monthly', 'Monthly'), ('yearly', 'Yearly')
    ], validators=[DataRequired()])
    next_due_date = DateField('Next Due Date', validators=[DataRequired()])
    description = StringField('Description', validators=[Optional()])
    submit = SubmitField('Save')
