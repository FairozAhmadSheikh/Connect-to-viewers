from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
from user_agents import parse as ua_parse
from bson.objectid import ObjectId
import os

# --- Load environment variables ---
load_dotenv()

# --- Initialize Flask ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')

# --- MongoDB Setup ---
MONGODB_URI = os.environ.get('MONGODB_URI')
if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI must be set as an environment variable.")

client = MongoClient(MONGODB_URI)
try:
    db = client.get_database()  # safer for serverless environments
except Exception:
    db_name = os.environ.get("MONGO_DB_NAME", "connect_db")
    db = client[db_name]

messages_col = db.messages

# --- Admin Credentials (from env only) ---
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD must be set in environment variables.")

# --- Helpers ---
def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get('admin') != True:
            return redirect(url_for('admin_login'))
        return fn(*args, **kwargs)
    return wrapper


# --- Public Routes ---
@app.route('/')
def index():
    msgs = list(messages_col.find({}, sort=[('createdAt', -1)]))
    for m in msgs:
        m['_id'] = str(m['_id'])
    return render_template('index.html', messages=msgs)


@app.route('/submit', methods=['POST'])
def submit():
    data = request.get_json() or request.form
    email = data.get('email', '').strip()
    username = data.get('username', '').strip()
    message = data.get('message', '').strip()

    if not email or not username or not message:
        return ("Missing fields", 400)

    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    ua = ua_parse(request.headers.get('User-Agent', ''))
    device = f"{ua.device.family} | {ua.os.family} | {ua.browser.family}"

    doc = {
        'email': email,
        'username': username,
        'message': message,
        'reply': None,
        'createdAt': datetime.utcnow(),
        'ip': ip,
        'device': device,
    }

    res = messages_col.insert_one(doc)
    doc['_id'] = str(res.inserted_id)

    # Do not expose IP/device publicly
    public_doc = {k: v for k, v in doc.items() if k not in ('ip', 'device')}
    return jsonify(public_doc), 201


# --- Admin Routes ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        return render_template('admin_login.html')

    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['admin'] = True
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_login.html', error='Invalid credentials')


@app.route('/dashboard')
@admin_required
def admin_dashboard():
    msgs = list(messages_col.find({}, sort=[('createdAt', -1)]))
    for m in msgs:
        m['_id'] = str(m['_id'])
    return render_template('admin_dashboard.html', messages=msgs)


@app.route('/reply/<id>', methods=['POST'])
@admin_required
def reply(id):
    reply_text = request.form.get('reply')
    if not reply_text:
        return ("Missing reply", 400)
    messages_col.update_one({'_id': ObjectId(id)}, {'$set': {'reply': reply_text}})
    return redirect(url_for('admin_dashboard'))


@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))


# --- API (optional public JSON feed) ---
@app.route('/api/messages')
def api_messages():
    msgs = list(messages_col.find({}, sort=[('createdAt', -1)]))
    out = []
    for m in msgs:
        out.append({
            'id': str(m['_id']),
            'email': m['email'],
            'username': m['username'],
            'message': m['message'],
            'reply': m.get('reply'),
            'createdAt': m['createdAt'].isoformat(),
        })
    return jsonify(out)


# --- Entry Point (only for local runs) ---
if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', 5000)))
