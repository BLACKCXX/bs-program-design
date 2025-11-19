import os
from datetime import timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from db import dict_cursor  # 本地直连工具

# 读取 .env
load_dotenv()

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-jwt")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)
CORS(app, resources={r"/api/*": {"origins": "*"}})
jwt = JWTManager(app)

@app.get("/api/health")
def health():
    return {"ok": True, "service": "server", "version": "v1"}, 200

# ---------- Auth: register / login / me （无需 ORM） ----------

@app.post("/api/auth/register")
def register():
    """
    输入: {email, username, password}
    规则: email/username 唯一; avatar_url 可选（不传则为 NULL）
    返回: {user, access_token}
    """
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    avatar_url = (data.get("avatar_url") or None)

    if not email or not username or not password:
        return jsonify(error="缺少邮箱/用户名/密码"), 400
    if len(password) < 6:
        return jsonify(error="密码至少 6 位"), 400

    pwd_hash = generate_password_hash(password)

    try:
        with dict_cursor() as (conn, cur):
            # 唯一性检查（也可以依赖表上 UNIQUE 索引并捕获 1062 错误）
            cur.execute("SELECT id FROM users WHERE email=%s OR username=%s LIMIT 1;", (email, username))
            if cur.fetchone():
                return jsonify(error="邮箱或用户名已存在"), 409

            cur.execute(
                "INSERT INTO users (username, email, password_hash, avatar_url) VALUES (%s,%s,%s,%s);",
                (username, email, pwd_hash, avatar_url)
            )
            user_id = cur.lastrowid
            cur.execute("SELECT id, username, email, avatar_url, created_at FROM users WHERE id=%s;", (user_id,))
            user = cur.fetchone()

        token = create_access_token(identity=str(user["id"]))
        return jsonify(user=user, access_token=token), 201
    except Exception as e:
        # 若是唯一约束导致的错误（MySQL 1062），给出更友好提示
        msg = getattr(e, "args", [None])[0]
        if msg == 1062:
            return jsonify(error="邮箱或用户名已存在"), 409
        return jsonify(error=f"服务器异常: {e}"), 500

@app.post("/api/auth/login")
def login():
    """
    输入: {email/password} 或 {username/password}
    """
    data = request.get_json() or {}
    identifier = (data.get("email") or data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    if not identifier or not password:
        return jsonify(error="缺少账号/密码"), 400

    # 根据是否包含 @ 判断是邮箱还是用户名
    cond_field = "email" if "@" in identifier else "username"

    with dict_cursor() as (conn, cur):
        cur.execute(f"SELECT id, username, email, avatar_url, password_hash FROM users WHERE {cond_field}=%s LIMIT 1;", (identifier,))
        user = cur.fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify(error="账号或密码错误"), 401

    # 删掉敏感字段
    user.pop("password_hash", None)
    token = create_access_token(identity=str(user["id"]))
    return jsonify(user=user, access_token=token), 200

@app.get("/api/me")
@jwt_required()
def me():
    user_id = get_jwt_identity()
    with dict_cursor() as (conn, cur):
        cur.execute("SELECT id, username, email, avatar_url, created_at FROM users WHERE id=%s;", (user_id,))
        user = cur.fetchone()
    if not user:
        return jsonify(error="用户不存在"), 404
    return jsonify(user), 200

if __name__ == "__main__":
    # 开发启动
    app.run(host="0.0.0.0", port=8000, debug=True)
