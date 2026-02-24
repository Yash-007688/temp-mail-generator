from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from temp_mail_generator import TempMailGenerator
import os
import hashlib
import secrets
import datetime
from db import init_db, create_user, find_user_by_username, find_user_by_id, update_user_preferences, update_user_api_key, update_user_api_key_with_quota


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-1337-fix")
init_db()


def get_mail_instance():
    """Returns a TempMailGenerator instance restored from session state."""
    m = TempMailGenerator()
    m.email = session.get("mail_email")
    m.login = session.get("mail_login")
    m.domain = session.get("mail_domain")
    m.provider = session.get("mail_provider", "1secmail")
    m.mailtm_token = session.get("mail_token")
    return m

def save_mail_to_session(m):
    """Saves TempMailGenerator state back to session."""
    session["mail_email"] = m.email
    session["mail_login"] = m.login
    session["mail_domain"] = m.domain
    session["mail_provider"] = m.provider
    session["mail_token"] = m.mailtm_token


@app.route("/health", methods=["GET"]) 
def health():
    return jsonify({"status": "ok"})

@app.route("/", methods=["GET"]) 
def index():
    return render_template("index.html")

@app.route("/dashboard", methods=["GET"])
def dashboard():
    return render_template("dashboard.html")


@app.route("/domains", methods=["GET"]) 
def domains():
    mail = get_mail_instance()
    return jsonify({"domains": mail.get_available_domains()})


@app.route("/generate/random", methods=["POST"]) 
def generate_random():
    data = request.get_json(silent=True) or {}
    length = data.get("length", 10)
    mail = get_mail_instance()
    email = mail.generate_random_email(length=length)
    save_mail_to_session(mail)
    return jsonify({"email": email})


@app.route("/generate/custom", methods=["POST"]) 
def generate_custom():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    domain = data.get("domain")
    if not username:
        return jsonify({"error": "username is required"}), 400
    # Restrict custom domain generation to logged-in users
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "login required"}), 401
    
    user = find_user_by_id(int(uid))
    if not user or user["plan"] == "free":
        return jsonify({"error": "₹99 Starter plan or higher required for custom identities"}), 403
    
    mail = get_mail_instance()
    email = mail.generate_custom_email(username=username, domain=domain)
    save_mail_to_session(mail)
    return jsonify({"email": email})


@app.route("/inbox", methods=["GET"]) 
def get_inbox():
    mail = get_mail_instance()
    inbox = mail.get_inbox()
    save_mail_to_session(mail) # Provider might have switched
    return jsonify({"email": mail.email, "messages": inbox})


@app.route("/read/<email_id>", methods=["GET"]) 
def read_email(email_id):
    # mail.tm uses string IDs, 1secmail uses ints. Let's keep it flexible.
    mail = get_mail_instance()
    data = mail.read_email(email_id)
    if not data:
        return jsonify({"error": "email not found or no email selected"}), 404
    return jsonify(data)


@app.route("/export", methods=["POST"]) 
def export_inbox():
    data = request.get_json(silent=True) or {}
    output_dir = data.get("output_dir", "inbox")
    os.makedirs(output_dir, exist_ok=True)
    mail = get_mail_instance()
    files = mail.export_inbox(output_dir)
    return jsonify({
        "saved": len(files),
        "files": files,
        "summary": os.path.join(output_dir, "inbox_summary.txt"),
    })


# -------- Auth --------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


@app.route("/login", methods=["GET"]) 
def login_page():
    return render_template("login.html")


@app.route("/register", methods=["GET"]) 
def register_page():
    return render_template("register.html")


@app.route("/signup", methods=["POST"]) 
def signup():
    data = request.get_json(silent=True) or request.form or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    plan = (data.get("plan") or "free").strip().lower()
    
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    
    # is_premium is true for any paid plan
    is_premium = plan in ['starter', 'pro', 'enterprise', 'api']
    
    ok, err = create_user(username, hash_password(password), plan=plan, is_premium=is_premium)
    if not ok:
        return jsonify({"error": err or "failed to create user"}), 400
    user = find_user_by_username(username)
    session["user_id"] = int(user["id"]) if user else None
    return jsonify({"ok": True, "redirect": "/dashboard"})


@app.route("/login", methods=["POST"]) 
def login():
    data = request.get_json(silent=True) or request.form or {}
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    user = find_user_by_username(username)
    if not user or user["password_hash"] != hash_password(password):
        return jsonify({"error": "invalid credentials"}), 401
    session["user_id"] = int(user["id"])
    return jsonify({"ok": True, "redirect": "/dashboard"})


@app.route("/logout", methods=["POST"]) 
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/me", methods=["GET"]) 
def me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"user": None})
    user = find_user_by_id(int(uid))
    if not user:
        session.pop("user_id", None)
        return jsonify({"user": None})
    return jsonify({
        "user": {
            "id": int(user["id"]),
            "username": user["username"],
            "plan": user["plan"],
            "is_premium": bool(user["is_premium"]),
            "preferences": user["preferences_json"],
            "api_key": user.get("api_key")
        }
    })


@app.route("/settings", methods=["POST"])
def update_settings():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "login required"}), 401
    
    user = find_user_by_id(int(uid))
    if not user:
        return jsonify({"error": "user not found"}), 404
    
    if user["plan"] == "free":
        return jsonify({"error": "₹99 Starter plan or higher required to save settings"}), 403
    
    data = request.get_json(silent=True) or {}
    import json
    updated = update_user_preferences(int(uid), json.dumps(data))
    
    if updated:
        return jsonify({"ok": True, "message": "Settings preserved securely"})
    return jsonify({"error": "Failed to update settings"}), 500


@app.route("/api", methods=["GET"])
def api_docs():
    return render_template("api.html")

@app.route("/apikey", methods=["GET"])
def api_key_page():
    return render_template("apikey.html")

@app.route("/apikey/create", methods=["POST"])
def create_api_key():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "login required"}), 401
    user = find_user_by_id(int(uid))
    if not user:
        return jsonify({"error": "user not found"}), 404
    if user["plan"] == "free":
        return jsonify({"error": "₹99 Starter plan or higher required for API key"}), 403
    today = datetime.date.today().isoformat()
    last_date = user["api_key_last_generated_at"]
    count = int(user["daily_api_key_count"] or 0)
    if last_date == today and count >= 2:
        return jsonify({"error": "daily limit reached", "limit": 2}), 429
    if last_date != today:
        count = 0
    key = "tm_" + secrets.token_urlsafe(32)
    count += 1
    ok = update_user_api_key_with_quota(int(uid), key, today, count)
    if not ok:
        return jsonify({"error": "failed to generate api key"}), 500
    return jsonify({"api_key": key, "generated_today": count, "limit": 2})


if __name__ == "__main__":
    # Run the development server: python main.py
    app.run(host="0.0.0.0", port=5000, debug=True)
