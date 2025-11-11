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


# Admin credentials (hard-coded)
ADMIN_USERNAME = os.environ.get('USERNAME')
ADMIN_PASSWORD = os.environ.get('PASSWORD')


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
    username = request.form.get('username')
    password = request.form.get('password')
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        session['admin'] = True
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html', error='Invalid credentials')