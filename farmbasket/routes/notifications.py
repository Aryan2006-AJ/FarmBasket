from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user

from farmbasket.services.notification_service import NotificationService

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.route("/")
@login_required
def list_notifications():
    notes = NotificationService.list_for_user(current_user.id, limit=50)
    unread_ids = {n.id for n in notes if not n.is_read}
    NotificationService.mark_all_read(current_user.id)
    return render_template("notifications/list.html", notifications=notes, unread_ids=unread_ids)


@notifications_bp.route("/api/unread-count")
@login_required
def unread_count():
    return jsonify({"count": NotificationService.unread_count(current_user.id)})
