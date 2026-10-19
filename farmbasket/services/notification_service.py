from farmbasket.extensions import db, socketio
from farmbasket.models import Notification


class NotificationService:
    """Creates in-app notifications and pushes them live over WebSocket when
    the recipient has a page open."""

    @staticmethod
    def notify(user_id, message, category="info", link=None):
        note = Notification(user_id=user_id, message=message, category=category, link=link)
        db.session.add(note)
        db.session.commit()

        # Delivered to the user's private room if they are connected.
        socketio.emit(
            "notification",
            {
                "id": note.id,
                "message": note.message,
                "category": note.category,
                "link": note.link,
                "created_at": note.created_at.strftime("%d %b, %I:%M %p"),
            },
            to=f"user_{user_id}",
        )
        return note

    @staticmethod
    def unread_count(user_id):
        return Notification.query.filter_by(user_id=user_id, is_read=False).count()

    @staticmethod
    def list_for_user(user_id, limit=20):
        return (
            Notification.query.filter_by(user_id=user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def mark_read(user_id, notification_id):
        note = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
        if note:
            note.is_read = True
            db.session.commit()
        return note

    @staticmethod
    def mark_all_read(user_id):
        Notification.query.filter_by(user_id=user_id, is_read=False).update({"is_read": True})
        db.session.commit()
