# user_manager.py
import json
import hashlib
from datetime import datetime
from typing import Optional, Dict
from config import USER_DB_FILE

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> Dict:
    try:
        with open(USER_DB_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_users(users: Dict):
    with open(USER_DB_FILE, "w") as f:
        json.dump(users, f, indent=2)

def register(username: str, password: str, preferences: dict = None) -> bool:
    users = load_users()
    if username in users:
        return False
    users[username] = {
        "password": hash_password(password),
        "preferences": preferences or {
            "ppt_theme": "default",
            "font_size": "11pt",
            "include_toc": True,
            "handout_detail": "medium"
        },
        "created_at": datetime.now().isoformat()
    }
    save_users(users)
    return True

def login(username: str, password: str) -> Optional[Dict]:
    users = load_users()
    user = users.get(username)
    if user and user["password"] == hash_password(password):
        return user
    return None

def update_preferences(username: str, new_prefs: dict):
    users = load_users()
    if username in users:
        users[username]["preferences"].update(new_prefs)
        save_users(users)