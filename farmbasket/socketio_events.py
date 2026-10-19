"""Flask-SocketIO event handlers. Each logged-in user joins a private room
named 'user_<id>' on connect, so NotificationService can push live events
straight to them (see farmbasket/services/notification_service.py)."""
from flask_login import current_user
from flask_socketio import join_room

from farmbasket.extensions import socketio


@socketio.on("connect")
def handle_connect():
    if current_user.is_authenticated:
        join_room(f"user_{current_user.id}")


@socketio.on("disconnect")
def handle_disconnect():
    pass
