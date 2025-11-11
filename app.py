from flask import Flask, render_template, request, redirect, url_for, session, jsonify, abort
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
import os
from user_agents import parse as ua_parse
from bson.objectid import ObjectId

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'dev-secret'

# Mongo
MONGODB_URI = os.environ.get('MONGODB_URI')
if not MONGODB_URI:
    raise RuntimeError('Set MONGODB_URI in environment')
client = MongoClient(MONGODB_URI)
db = client.get_default_database()
messages_col = db.messages


ADMIN_USERNAME = os.environ.get('USERNAME', 'Fairoz')
ADMIN_PASSWORD = os.environ.get('PASSWORD', 'Fairoz788952@')

# --- DEBUG (safe fallback + visibility) ---
print(f"[DEBUG] ADMIN_USERNAME={repr(ADMIN_USERNAME)} | ADMIN_PASSWORD={repr(ADMIN_PASSWORD)}")



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
    # ensure fallback creds
    global ADMIN_USERNAME, ADMIN_PASSWORD
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

    if request.method == 'GET':
        return render_template('admin_login.html')

    # --- Diagnostics: dump everything we can ---
    print("----- ADMIN LOGIN ATTEMPT -----")
    print("ENV USERNAME   :", repr(os.environ.get('ADMIN_USERNAME')))
    print("ENV PASSWORD   :", repr(os.environ.get('ADMIN_PASSWORD')))
    print("APP ADMIN_USER :", repr(ADMIN_USERNAME))
    print("APP ADMIN_PASS :", repr(ADMIN_PASSWORD))
    try:
        raw = request.get_data(as_text=True)
    except Exception as e:
        raw = f"<error reading raw: {e}>"
    print("RAW REQUEST BODY:", repr(raw))
    print("REQUEST FORM KEYS:", list(request.form.keys()))
    for k in request.form.keys():
        print(f" request.form[{k}] = {repr(request.form.get(k))}")
    # Also show headers (so we can see content-type, etc.)
    print("REQUEST HEADERS:")
    for h, v in request.headers.items():
        print(" ", h, ":", repr(v))
    print("----- END DIAG -----")

    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()

    # final compare (case-sensitive)
    if username == (ADMIN_USERNAME or '').strip() and password == (ADMIN_PASSWORD or '').strip():
        session['admin'] = True
        print("[DEBUG] Admin login SUCCESS")
        return redirect(url_for('admin_dashboard'))

    print("[DEBUG] Admin login FAILED; compared", repr(username), "vs", repr(ADMIN_USERNAME), " and ", repr(password), "vs", repr(ADMIN_PASSWORD))
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