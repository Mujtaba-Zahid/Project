from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, SelectField, DateField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional


class InvestmentForm(FlaskForm):
    asset_name = StringField('Asset Name', validators=[DataRequired()])
    asset_type = SelectField('Asset Type', choices=[
        ('stock', 'Stock'), ('gold', 'Gold'), ('property', 'Property'),
        ('fixed_deposit', 'Fixed Deposit'), ('crypto', 'Crypto'), ('other', 'Other')
    ], validators=[DataRequired()])
    purchase_amount = DecimalField('Purchase Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    current_value = DecimalField('Current Value', validators=[DataRequired(), NumberRange(min=0)])
    purchase_date = DateField('Purchase Date', validators=[DataRequired()])
    currency = StringField('Currency', default='PKR', validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional()])
    submit = SubmitField('Save Investment')


class SellForm(FlaskForm):
    sold_amount = DecimalField('Sold Amount', validators=[DataRequired(), NumberRange(min=0.01)])
    sold_date = DateField('Sold Date', validators=[DataRequired()])
    submit = SubmitField('Mark as Sold')
