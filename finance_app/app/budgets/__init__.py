from flask import Blueprint

budgets_bp = Blueprint('budgets', __name__, url_prefix='/budgets')

from . import routes  # noqa: E402, F401
