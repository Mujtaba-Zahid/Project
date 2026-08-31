"""Notification service — in-app + email notifications."""
from ..extensions import db, mail
from ..models.notification import Notification
from flask_mail import Message
from flask import current_app


def create_notification(user_id, notif_type, title, message):
    """Create an in-app notification record."""
    notif = Notification(
        user_id=user_id,
        type=notif_type,
        title=title,
        message=message,
    )
    db.session.add(notif)
    # Don't commit here — let the caller manage the transaction
    return notif


def send_email_notification(to_email, subject, body):
    """Send an email notification via Flask-Mail."""
    try:
        sender = current_app.config.get('MAIL_DEFAULT_SENDER')
        if not sender:
            current_app.logger.warning('MAIL_DEFAULT_SENDER not configured, skipping email.')
            return False

        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=body,
            sender=sender,
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f'Failed to send email to {to_email}: {e}')
        return False


def get_unread_count(user_id):
    """Get count of unread notifications."""
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()


def get_notifications(user_id, limit=20):
    """Get recent notifications for a user."""
    return Notification.query.filter_by(user_id=user_id).order_by(
        Notification.created_at.desc()
    ).limit(limit).all()


def mark_as_read(notification_id, user_id):
    """Mark a notification as read."""
    notif = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if notif:
        notif.is_read = True
        db.session.commit()
    return notif


def mark_all_read(user_id):
    """Mark all notifications as read."""
    Notification.query.filter_by(user_id=user_id, is_read=False).update({'is_read': True})
    db.session.commit()
