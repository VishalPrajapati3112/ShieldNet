# app/lan_transfer.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, current_app
from flask_login import login_required, current_user, logout_user
import os, random, socket, shutil
from werkzeug.utils import secure_filename

lan_bp = Blueprint('lan', __name__, url_prefix='/lan')

# single global to hold active session info (only one LAN session at a time)
ACTIVE_SESSIONS = {
    # structure example:
    # 'otp': 123456,
    # 'username': 'sender_name',
    # 'password': 'secretpass',
    # 'folder': '/abs/path/to/uploads/session_123456',
    # 'owner': current_user.id
}
BASE_UPLOAD_DIR = None


@lan_bp.before_app_request
def ensure_base_upload_dir():
    """Ensure base uploads dir exists and store it in BASE_UPLOAD_DIR"""
    global BASE_UPLOAD_DIR
    if not BASE_UPLOAD_DIR:
        BASE_UPLOAD_DIR = current_app.config.get('UPLOAD_FOLDER') or os.path.join(os.getcwd(), 'uploads')
        os.makedirs(BASE_UPLOAD_DIR, exist_ok=True)


def get_local_ip():
    """Return LAN IP (best-effort)"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def clear_folder(path):
    """Safely remove a folder and everything inside it"""
    try:
        if path and os.path.exists(path):
            shutil.rmtree(path)
    except Exception as e:
        # don't fail hard; log to console
        print(f"[lan_transfer] error removing folder {path}: {e}")


@lan_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_session():
    """
    Sender creates a new LAN session.
    Behavior:
    - Removes any previous session folder (so old files won't be visible)
    - Creates new session_<OTP> folder under BASE_UPLOAD_DIR
    - Stores session info in ACTIVE_SESSIONS
    - Prints sender/receiver links + OTP to terminal (so sender can share)
    """
    global ACTIVE_SESSIONS, BASE_UPLOAD_DIR

    if request.method == 'POST':
        username = (request.form.get('username') or "").strip()
        password = (request.form.get('password') or "").strip()

        if not username or not password:
            flash("Please provide username and password to create a session.", "warning")
            return redirect(url_for('lan.create_session'))

        # Delete any previous session folder(s)
        # We remove only folders that match the naming convention session_<digits>
        if BASE_UPLOAD_DIR and os.path.exists(BASE_UPLOAD_DIR):
            for ent in os.listdir(BASE_UPLOAD_DIR):
                path = os.path.join(BASE_UPLOAD_DIR, ent)
                if os.path.isdir(path) and ent.startswith("session_"):
                    clear_folder(path)

        # create a new session folder for this LAN session
        otp = random.randint(100000, 999999)
        session_folder = os.path.join(BASE_UPLOAD_DIR, f"session_{otp}")
        os.makedirs(session_folder, exist_ok=True)

        # store session
        ACTIVE_SESSIONS.clear()
        ACTIVE_SESSIONS.update({
            "otp": otp,
            "username": username,
            "password": password,
            "folder": session_folder,
            "owner": current_user.get_id()  # record owner id for safety
        })

        ip = get_local_ip()
        flash("LAN Session created successfully! Share the receiver link and OTP.", "success")

        # Print the links (so sender can copy & share)
        print("\n===== LAN SESSION STARTED =====")
        print(f"Sender panel (local): http://127.0.0.1:5000/lan/panel")
        print(f"Receiver join link: http://{ip}:5000/lan/join")
        print(f"Username: {username}")
        print(f"Password: {password}")
        print(f"OTP: {otp}")
        print(f"Session folder: {session_folder}")
        print("=================================\n")

        return redirect(url_for('lan.panel'))

    return render_template('lan_create.html')


@lan_bp.route('/join', methods=['GET', 'POST'])
def join_session():
    """
    Receiver opens the join page (anyone on LAN).
    They must provide username + password + OTP as given by sender.
    """
    if request.method == 'POST':
        username = (request.form.get('username') or "").strip()
        password = (request.form.get('password') or "").strip()
        otp = (request.form.get('otp') or "").strip()

        if (not ACTIVE_SESSIONS
                or username != str(ACTIVE_SESSIONS.get('username'))
                or password != str(ACTIVE_SESSIONS.get('password'))
                or str(otp) != str(ACTIVE_SESSIONS.get('otp'))):
            flash("Invalid credentials or session not active.", "error")
            return redirect(url_for('lan.join_session'))

        flash("Connected to LAN session.", "success")
        return redirect(url_for('lan.panel'))

    # GET shows the join form
    return render_template('lan_join.html')


@lan_bp.before_request
def require_active_session_for_panel():
    """
    If user tries to access panel/upload/download/files while no active session exists,
    redirect to join/create page with message.
    """
    # allow create/join endpoints always
    allowed = ('lan.create_session', 'lan.join_session', 'lan.create', 'lan.join')
    # request.endpoint can be None in some contexts; guard against that
    endpoint = (request.endpoint or "")
    if endpoint.startswith('lan.') and endpoint not in allowed:
        # If there is no active session, redirect
        if not ACTIVE_SESSIONS:
            flash("Session expired or not active. Ask sender to create a new session.", "error")
            return redirect(url_for('lan.join_session'))


@lan_bp.route('/panel')
def panel():
    """
    Shared dashboard for sender & receivers.
    Lists files inside the current session folder (if any).
    """
    folder = ACTIVE_SESSIONS.get('folder')
    files = []
    if folder and os.path.exists(folder):
        files = sorted(os.listdir(folder))
    return render_template('lan_panel.html', files=files, session_info=ACTIVE_SESSIONS)


@lan_bp.route('/upload', methods=['POST'])
def upload_file():
    """
    Upload a file into the active session folder.
    Both sender and receivers (who joined) can upload.
    """
    folder = ACTIVE_SESSIONS.get('folder')
    if not folder:
        flash("No active session to upload to.", "error")
        return redirect(url_for('lan.join_session'))

    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('lan.panel'))

    f = request.files['file']
    if not f or f.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('lan.panel'))

    filename = secure_filename(f.filename)
    save_path = os.path.join(folder, filename)
    f.save(save_path)
    flash(f"Uploaded: {filename}", "success")
    return redirect(url_for('lan.panel'))


@lan_bp.route('/files', methods=['GET'])
def list_files():
    """Return JSON list of current session files (used by client if needed)."""
    folder = ACTIVE_SESSIONS.get('folder')
    if not folder or not os.path.exists(folder):
        return jsonify([])
    return jsonify(sorted(os.listdir(folder)))


@lan_bp.route('/download/<path:filename>')
def download_file(filename):
    """Download a file from the active session folder."""
    folder = ACTIVE_SESSIONS.get('folder')
    if not folder or not os.path.exists(os.path.join(folder, filename)):
        flash("File not found or session ended.", "error")
        return redirect(url_for('lan.panel'))
    return send_from_directory(folder, filename, as_attachment=True)


@lan_bp.route('/end', methods=['GET'])
@login_required
def end_session():
    """
    Sender ends the session (manual). This will:
    - delete the session folder and files
    - clear ACTIVE_SESSIONS
    - flash a message
    """
    # ensure only owner can end (simple check)
    owner = ACTIVE_SESSIONS.get('owner')
    # 'owner' may be missing if you didn't store it; allow current_user to end anyway if owner matches or not set
    if owner and str(owner) != str(current_user.get_id()):
        flash("Only the session owner can end the session.", "error")
        return redirect(url_for('lan.panel'))

    folder = ACTIVE_SESSIONS.get('folder')
    if folder:
        clear_folder(folder)

    ACTIVE_SESSIONS.clear()
    flash("Session ended and shared files removed.", "info")
    return redirect(url_for('main.dashboard'))

# --- export symbols for import in app.py ---
__all__ = ["ACTIVE_SESSIONS", "clear_folder"]


import shutil
import os

# 🔹 Global session dictionary
ACTIVE_SESSIONS = {}

def clear_folder(folder_path):
    """Safely delete all files & folders inside the given folder."""
    try:
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path, ignore_errors=True)
            print(f"[cleanup] Folder deleted: {folder_path}")
        else:
            print(f"[cleanup] Folder not found: {folder_path}")
    except Exception as e:
        print(f"[cleanup error] Failed to delete {folder_path}: {e}")
