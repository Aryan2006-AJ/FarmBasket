from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
from apscheduler.schedulers.background import BackgroundScheduler

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

# async_mode="threading" needs no extra dependency (no eventlet/gevent) and
# works reliably cross-platform (including Windows) for a demo-scale app.
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")

scheduler = BackgroundScheduler(daemon=True)
