from flask import Blueprint

investments_bp = Blueprint('investments', __name__, url_prefix='/investments')

from . import routes  # noqa: E402, F401
