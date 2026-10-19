import os

from farmbasket import create_app
from farmbasket.extensions import socketio

app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FARMBASKET_DEBUG", "false").lower() in ("1", "true", "yes")
    host = os.environ.get("FARMBASKET_HOST", "127.0.0.1")
    port = int(os.environ.get("FARMBASKET_PORT", "5000"))
    # socketio.run serves normal requests and WebSocket connections together.
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=False, allow_unsafe_werkzeug=True)
