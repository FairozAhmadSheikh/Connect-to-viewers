from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
import os
import logging
from user_agents import parse as ua_parse
from bson.objectid import ObjectId
import hmac

from dotenv import load_dotenv
load_dotenv(override=True)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'dev-secret'

# Mongo
MONGODB_URI = os.environ.get('MONGODB_URI')
if not MONGODB_URI:
    raise RuntimeError('Set MONGODB_URI in environment')
client = MongoClient(MONGODB_URI)
db = client.get_default_database()
messages_col = db.messages


ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

if not ADMIN_USERNAME or not ADMIN_PASSWORD:
    # Safe, non-secreting error message (no real credentials shown)
    raise RuntimeError(
        "ADMIN_USERNAME and ADMIN_PASSWORD must be set in the environment or in a .env file.\n\n"
        "Example .env (DO NOT copy real credentials into source):\n"
        "ADMIN_USERNAME=your_admin_username\n"
        "ADMIN_PASSWORD=your_admin_password\n\n"
        "After updating .env, restart the Flask server."
    )
# setup a module-level logger (no secrets printed)
logger = logging.getLogger("flask_app")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

def _mask(value: str, head: int = 2, tail: int = 0):
    if not value:
        return "None"
    if len(value) <= head + tail:
        return "*" * len(value)
    return value[:head] + ("*" * (len(value) - head - tail)) + (value[-tail:] if tail else "")

# Log only masked metadata for debugging
logger.info("ADMIN_USERNAME loaded: %s", _mask(ADMIN_USERNAME, head=2))
logger.info("ADMIN_PASSWORD loaded: %s (length=%d)", "*" * min(4, len(ADMIN_PASSWORD)), len(ADMIN_PASSWORD))


# Helpers
def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get('admin') != True:
            return redirect(url_for('admin_login'))
        return fn(*args, **kwargs)
    return wrapper

@app.route('/')
def index():
    msgs = list(messages_col.find({}, sort=[('createdAt', -1)]))
    # prepare public view: omit ip/device
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


    # capture IP and device
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    ua = request.headers.get('User-Agent', '')
    parsed = ua_parse(ua)
    device = f"{parsed.device.family} | {parsed.os.family} | {parsed.browser.family}"


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
    # Do not return ip/device in response to public
    public_doc = {k: v for k, v in doc.items() if k not in ('ip', 'device')}
    return jsonify(public_doc), 201



@app.route('/admin', methods=['GET','POST'])
def admin_login():
    if request.method == 'GET':
        return render_template('admin_login.html')

    # get form values and strip whitespace
    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()

    # use constant-time comparison to avoid timing attacks
    user_match = hmac.compare_digest(username, ADMIN_USERNAME)
    pass_match = hmac.compare_digest(password, ADMIN_PASSWORD)

    if user_match and pass_match:
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
    if reply_text is None:
        return ("Missing reply", 400)
    messages_col.update_one({'_id': ObjectId(id)}, {'$set': {'reply': reply_text}})
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

# API endpoint to get public messages as JSON
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
        'createdAt': m['createdAt'].isoformat()
        })
    return jsonify(out)
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))