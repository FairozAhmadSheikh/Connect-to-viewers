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
