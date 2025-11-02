# app.py

import eventlet
eventlet.monkey_patch()

import os
import sys
import signal
import atexit
import importlib.util
import socket



# Ensure 'app' package is importable
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
APP_DIR = os.path.join(BASE_DIR, "app")

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app import create_app, db, socketio

app = create_app()

def cleanup_on_exit(*args):
    print("\n[server] Shutting down gracefully...")

# Register cleanup handlers
signal.signal(signal.SIGINT, cleanup_on_exit)
signal.signal(signal.SIGTERM, cleanup_on_exit)
atexit.register(cleanup_on_exit)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    # Detect LAN IP automatically
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "localhost"

    print("[server] Secure Transfer Server running:")
    print(f"   ➜ Local access: http://127.0.0.1:5000")
    print(f"   ➜ LAN access:   http://{local_ip}:5000")
    print("---------------------------------------------------")

    socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=False)
