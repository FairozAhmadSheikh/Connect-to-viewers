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