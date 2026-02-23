from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from temp_mail_generator import TempMailGenerator
import os
import hashlib
from db import init_db, create_user, find_user_by_username, find_user_by_id


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
init_db()


# Single generator instance keeps the selected email/login/domain in memory
mail = TempMailGenerator()


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
    return jsonify({"domains": mail.get_available_domains()})


@app.route("/generate/random", methods=["POST"]) 
def generate_random():
    data = request.get_json(silent=True) or {}
    length = data.get("length", 10)
    email = mail.generate_random_email(length=length)
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
    email = mail.generate_custom_email(username=username, domain=domain)
    return jsonify({"email": email})


@app.route("/inbox", methods=["GET"]) 
def get_inbox():
    inbox = mail.get_inbox()
    return jsonify({"email": mail.email, "messages": inbox})


@app.route("/read/<int:email_id>", methods=["GET"]) 
def read_email(email_id: int):
    data = mail.read_email(email_id)
    if not data:
        return jsonify({"error": "email not found or no email selected"}), 404
    return jsonify(data)


@app.route("/export", methods=["POST"]) 
def export_inbox():
    data = request.get_json(silent=True) or {}
    output_dir = data.get("output_dir", "inbox")
    os.makedirs(output_dir, exist_ok=True)
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
    session.pop("user_id", None)
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
            "preferences": user["preferences_json"]
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


if __name__ == "__main__":
    # Run the development server: python main.py
    app.run(host="0.0.0.0", port=5000, debug=True)


