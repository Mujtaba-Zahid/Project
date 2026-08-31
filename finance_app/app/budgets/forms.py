from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, DateField, SubmitField
from wtforms.validators import DataRequired, NumberRange


class BudgetForm(FlaskForm):
    category_id = SelectField('Category', coerce=int, validators=[DataRequired()])
    monthly_limit = DecimalField('Monthly Limit', validators=[DataRequired(), NumberRange(min=1)])
    month = DateField('Month', validators=[DataRequired()])
    submit = SubmitField('Save Budget')
