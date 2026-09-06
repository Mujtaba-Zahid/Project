from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional


class LoginForm(FlaskForm):
    """Email/password login form."""
    email = StringField('Email', validators=[DataRequired(), Email()], filters=[lambda x: x.strip().lower() if x else ''])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me', default=True)
    submit = SubmitField('Sign In')


class RegisterForm(FlaskForm):
    """New user registration form."""
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)], filters=[lambda x: x.strip() if x else ''])
    email = StringField('Email', validators=[DataRequired(), Email()], filters=[lambda x: x.strip().lower() if x else ''])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password', message='Passwords must match.')
    ])
    submit = SubmitField('Create Account')
