from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    """
    After login, user arrives here.
    Detects whether running in LAN or Online environment.
    """
    host = request.host
    if 'localhost' in host or '127.0.0.1' in host:
        mode = 'lan'
    else:
        mode = 'online'

    return render_template('dashboard.html', user=current_user, mode=mode)
