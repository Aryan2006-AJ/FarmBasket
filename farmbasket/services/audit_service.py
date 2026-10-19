from farmbasket.extensions import db
from farmbasket.models import AuditLog


class AuditService:

    @staticmethod
    def log(actor_id, action, target_type=None, target_id=None, details=None):
        entry = AuditLog(
            actor_id=actor_id, action=action, target_type=target_type,
            target_id=target_id, details=details,
        )
        db.session.add(entry)
        db.session.commit()
        return entry

    @staticmethod
    def recent(limit=100):
        return AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
