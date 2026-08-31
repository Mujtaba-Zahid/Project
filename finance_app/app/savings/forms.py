from flask_wtf import FlaskForm
from wtforms import StringField, DecimalField, DateField, SelectField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional


class SavingsGoalForm(FlaskForm):
    goal_name = StringField('Goal Name', validators=[DataRequired()])
    target_amount = DecimalField('Target Amount', validators=[DataRequired(), NumberRange(min=1)])
    deadline = DateField('Deadline', validators=[Optional()])
    submit = SubmitField('Save Goal')


class ContributionForm(FlaskForm):
    amount = DecimalField('Amount', validators=[DataRequired(), NumberRange(min=1)])
    account_id = SelectField('From Account', coerce=int, validators=[Optional()])
    note = StringField('Note', validators=[Optional()])
    submit = SubmitField('Contribute')
