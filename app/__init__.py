from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from flask_login import LoginManager
import os

db = SQLAlchemy()
socketio = SocketIO(cors_allowed_origins="*", message_queue=os.getenv("REDIS_URL", "redis://localhost:6379/0"))

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'secure_transfer_secret'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///secure_transfer.db'
    app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
    app.config['REDIS_URL'] = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    db.init_app(app)
    socketio.init_app(app)

    # ✅ sabhi blueprints register karo
    from . import models, auth, lan_transfer, online_transfer, main
    app.register_blueprint(auth.auth_bp)
    app.register_blueprint(lan_transfer.lan_bp)
    app.register_blueprint(online_transfer.bp)
    app.register_blueprint(main.main_bp)   # ✅ ye missing tha

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    from .models import User
    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    return app
