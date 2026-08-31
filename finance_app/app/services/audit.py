"""Audit logging service — replaces SQL audit_log inserts."""
from ..extensions import db
from ..models.audit_log import AuditLog


def log_action(table_name, operation, record_id, user_id=None,
               note=None, old_value=None, new_value=None):
    """Create an audit log entry.

    Args:
        table_name: Name of the affected table.
        operation: What happened (e.g., 'deposit', 'withdrawal', 'update', 'delete').
        record_id: ID of the affected record.
        user_id: Who performed the action.
        note: Human-readable note.
        old_value: JSON dict of values before change.
        new_value: JSON dict of values after change.
    """
    entry = AuditLog(
        user_id=user_id,
        table_name=table_name,
        operation=operation,
        record_id=record_id,
        note=note,
        old_value=old_value,
        new_value=new_value,
    )
    db.session.add(entry)
    # Don't commit — let the caller manage the transaction
    return entry
