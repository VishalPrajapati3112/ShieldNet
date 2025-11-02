from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, current_app, send_from_directory
from flask_login import login_required, current_user
from flask_socketio import emit, join_room, leave_room
import redis, os, json, time, secrets, shutil
from werkzeug.utils import secure_filename
from app import socketio

bp = Blueprint('online_transfer', __name__, url_prefix='/online')

# ---------- Redis Setup ----------
def get_redis():
    url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
    return redis.Redis.from_url(url)

def session_key(token): return f"session:{token}"
def participants_key(token): return f"{session_key(token)}:participants"
def files_key(token): return f"{session_key(token)}:files"

def make_token():
    r = get_redis()
    while True:
        token = secrets.token_urlsafe(6)
        if not r.exists(session_key(token)):
            return token

def session_folder(token):
    base = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.root_path, '..', 'uploads'))
    folder = os.path.abspath(os.path.join(base, token))
    os.makedirs(folder, exist_ok=True)
    return folder


# ---------- UI routes ----------

# ✅ Fix for BuildError — legacy alias
@bp.route('/index')
@login_required
def index():
    """Redirect old 'index' route to select_mode"""
    return redirect(url_for('online_transfer.select_mode'))


@bp.route('/')
@login_required
def select_mode():
    """Show Create / Join options"""
    return render_template('online_select.html')


@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_session():
    """Sender creates session with session_name, password, optional auto-expire"""
    r = get_redis()
    if request.method == 'POST':
        sess_name = (request.form.get('session_name') or current_user.username).strip()
        password = (request.form.get('password') or '').strip()
        auto_expire = request.form.get('auto_expire')

        try:
            auto_expire = int(auto_expire) * 60 if auto_expire else 0
        except Exception:
            auto_expire = 0

        token = make_token()
        folder = session_folder(token)

        data = {
            'owner_id': str(current_user.id),
            'owner_name': sess_name,
            'password': password,
            'created_at': str(int(time.time())),
            'closed': '0'
        }

        r.hset(session_key(token), mapping=data)
        r.sadd(participants_key(token), current_user.username)

        if auto_expire:
            r.expire(session_key(token), auto_expire)
            r.expire(participants_key(token), auto_expire)
            r.expire(files_key(token), auto_expire)
            r.hset(session_key(token), 'auto_expire', str(auto_expire))

        flash(f"Session created successfully. Share this token with receivers: {token}", "success")
        return redirect(url_for('online_transfer.session_panel', token=token))

    return render_template('online_create.html')


@bp.route('/join', methods=['GET', 'POST'])
@login_required
def join_session():
    """Receiver joins session with token + password"""
    r = get_redis()
    if request.method == 'POST':
        token = (request.form.get('token') or '').strip()
        password = (request.form.get('password') or '').strip()

        if not token:
            flash("Please provide a session token.", "warning")
            return redirect(url_for('online_transfer.join_session'))

        sess = r.hgetall(session_key(token))
        if not sess or sess.get(b'closed') == b'1':
            flash("Session not found or closed.", "danger")
            return redirect(url_for('online_transfer.join_session'))

        sess_password = sess.get(b'password', b'').decode()
        if sess_password and sess_password != password:
            flash("Incorrect password.", "danger")
            return redirect(url_for('online_transfer.join_session'))

        r.sadd(participants_key(token), current_user.username)

        socketio.emit('participants_update', {
            'participants': [p.decode() for p in r.smembers(participants_key(token))]
        }, room=token)

        flash(f"Joined session owned by {sess.get(b'owner_name').decode()}", "success")
        return redirect(url_for('online_transfer.session_panel', token=token))

    return render_template('online_join.html')


@bp.route('/session/<token>')
@login_required
def session_panel(token):
    """Shared dashboard for session"""
    r = get_redis()
    sess = r.hgetall(session_key(token))

    if not sess or sess.get(b'closed') == b'1':
        flash("Session not available.", "danger")
        return redirect(url_for('online_transfer.select_mode'))

    participants = [p.decode() for p in r.smembers(participants_key(token))]
    if current_user.username not in participants:
        flash("Please join the session first.", "warning")
        return redirect(url_for('online_transfer.join_session'))

    files = [f.decode() for f in r.lrange(files_key(token), 0, -1)]
    owner_name = sess.get(b'owner_name').decode()
    is_owner = (sess.get(b'owner_id').decode() == str(current_user.id))
    auto_expire = sess.get(b'auto_expire').decode() if sess.get(b'auto_expire') else ''

    return render_template('online_dashboard.html',
                           token=token,
                           files=files,
                           owner_name=owner_name,
                           participants=participants,
                           is_owner=is_owner,
                           auto_expire=auto_expire)


# ---------- File APIs ----------
@bp.route('/upload/<token>', methods=['POST'])
@login_required
def upload_file(token):
    """Upload file to session folder"""
    r = get_redis()
    sess = r.hgetall(session_key(token))
    if not sess or sess.get(b'closed') == b'1':
        return jsonify({'status': 'not_available'}), 404

    participants = [p.decode() for p in r.smembers(participants_key(token))]
    if current_user.username not in participants:
        return jsonify({'status': 'not_member'}), 403

    if 'file' not in request.files:
        return jsonify({'status': 'no_file'}), 400

    f = request.files['file']
    if not f or f.filename == '':
        return jsonify({'status': 'no_file'}), 400

    filename = secure_filename(f.filename)
    folder = session_folder(token)
    f.save(os.path.join(folder, filename))
    r.rpush(files_key(token), filename)

    socketio.emit('file_added', {'filename': filename, 'uploader': current_user.username}, room=token)
    return jsonify({'status': 'ok', 'filename': filename})


@bp.route('/download/<token>/<filename>')
@login_required
def download_file(token, filename):
    r = get_redis()
    sess = r.hgetall(session_key(token))
    if not sess or sess.get(b'closed') == b'1':
        flash("Session not available.", "danger")
        return redirect(url_for('online_transfer.select_mode'))

    participants = [p.decode() for p in r.smembers(participants_key(token))]
    if current_user.username not in participants:
        flash("You are not part of this session.", "danger")
        return redirect(url_for('online_transfer.select_mode'))

    folder = session_folder(token)
    safe = secure_filename(filename)
    if safe not in [f.decode() for f in r.lrange(files_key(token), 0, -1)]:
        flash("File not found.", "danger")
        return redirect(url_for('online_transfer.session_panel', token=token))
    return send_from_directory(folder, safe, as_attachment=True)


@bp.route('/end/<token>', methods=['POST'])
@login_required
def end_session(token):
    """Owner ends session — delete files + Redis keys"""
    r = get_redis()
    sess = r.hgetall(session_key(token))
    if not sess:
        return jsonify({'status': 'not_found'}), 404
    if sess.get(b'owner_id').decode() != str(current_user.id):
        return jsonify({'status': 'forbidden'}), 403

    r.hset(session_key(token), 'closed', '1')

    folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.root_path, '..', 'uploads')), token)
    try:
        if os.path.exists(folder):
            shutil.rmtree(folder)
    except Exception:
        pass

    r.delete(session_key(token))
    r.delete(participants_key(token))
    r.delete(files_key(token))

    socketio.emit('session_ended', {}, room=token)
    return jsonify({'status': 'ended'})


@bp.route('/set_auto_expire/<token>', methods=['POST'])
@login_required
def set_auto_expire(token):
    """Owner can set session auto timeout"""
    r = get_redis()
    sess = r.hgetall(session_key(token))
    if not sess:
        return jsonify({'status': 'not_found'}), 404
    if sess.get(b'owner_id').decode() != str(current_user.id):
        return jsonify({'status': 'forbidden'}), 403

    minutes = request.form.get('minutes')
    try:
        minutes = int(minutes)
    except Exception:
        return jsonify({'status': 'bad_request'}), 400

    seconds = minutes * 60
    r.expire(session_key(token), seconds)
    r.expire(participants_key(token), seconds)
    r.expire(files_key(token), seconds)
    r.hset(session_key(token), 'auto_expire', str(seconds))

    socketio.emit('auto_expire_set', {'minutes': minutes}, room=token)
    return jsonify({'status': 'ok', 'minutes': minutes})


# ---------- SocketIO events ----------
@socketio.on('join_room')
def handle_join(data):
    token = data.get('token')
    join_room(token)
    r = get_redis()
    participants = [p.decode() for p in r.smembers(participants_key(token))]
    emit('participants_update', {'participants': participants}, room=token)


@socketio.on('leave_room')
def handle_leave(data):
    token = data.get('token')
    leave_room(token)


# ---------- Background Janitor ----------
def janitor_loop():
    """Clean expired session folders"""
    import time
    while True:
        try:
            r = get_redis()
            for key in r.scan_iter(match='session:*'):
                if r.ttl(key) in (-1, -2):
                    continue
                if not r.exists(key):
                    token = key.decode().split(':', 1)[1]
                    folder = os.path.join(current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.root_path, '..', 'uploads')), token)
                    if os.path.exists(folder):
                        shutil.rmtree(folder)
            time.sleep(30)
        except Exception:
            time.sleep(5)

try:
    import threading
    t = threading.Thread(target=janitor_loop, daemon=True)
    t.start()
except Exception:
    pass
