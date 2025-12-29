'''
import os
from datetime import timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS
import os

from .db import dict_cursor  # 本地直连工具
# 注册图片相关蓝图（上传/列表/标签/静态文件）
from .routes_images import bp as images_bp


# 读取 .env
load_dotenv()

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-jwt")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.register_blueprint(images_bp)
jwt = JWTManager(app)

@app.get("/api/health")
def health():
    return {"ok": True, "service": "server", "version": "v1"}, 200

# ---------- Auth: register / login / me （无需 ORM） ----------

@app.post("/api/auth/register")
def register():
    """
    ???email, username, password
    - ????
    - ?? password_hash
    - ???avatar_url
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    #advise ??????? + ?? + ????
    if not email or not username or not password:
        return _err("??????", 400)
    if len(username) < 6:
        return _err("????? 6 ???", 400)
    if len(password) < 6:
        return _err("???? 6 ???", 400)
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return _err("???????", 400)

    # ????
    dup = query("SELECT id FROM users WHERE email=%s OR username=%s LIMIT 1", (email, username))
    if dup:
        return _err("?????????", 409)

    pwd_hash = generate_password_hash(password)
    uid = execute(
        "INSERT INTO users (email, username, password_hash, created_at) VALUES (%s, %s, %s, NOW())",
        (email, username, pwd_hash)
    )

    user = query(
        "SELECT id,email,username,avatar_url,created_at FROM users WHERE id=%s",
        (uid,)
    )[0]
    return _ok(_user_public(user), 201)

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
def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # JWT 秘钥（沿用你现有）
    app.config["JWT_SECRET"] = os.getenv("JWT_SECRET", "dev-secret")
    app.config["UPLOAD_DIR"] = os.path.abspath(os.path.join(os.path.dirname(__file__), os.getenv("UPLOAD_DIR","uploads")))
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024   # 整体上限

    # 注册图片路由
    from server.routes_images import bp as images_bp
    app.register_blueprint(images_bp)

    # 你原来的 auth 路由、健康检查等也一起注册...

    return app

if __name__ == "__main__":
    # 开发启动
    app = create_app()
    app.run(host="0.0.0.0", port=8000, debug=True)
    ###
    '''
# server/app.py
# -*- coding: utf-8 -*-
"""
B/S 程序设计 · 后端入口（App Factory）
- 统一通过 create_app() 构建 Flask 应用
- 使用 flask-jwt-extended 做鉴权
- 与 routes_images 蓝图对接（上传/列表/标签/静态文件）
- 支持 `python -m server.app` 启动

依赖：
  pip install Flask Flask-Cors flask-jwt-extended PyMySQL python-dotenv Pillow
"""

import os
from datetime import timedelta
from typing import Optional, Dict, Any
import re  #advise 校验邮箱格式

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# 包内导入（相对导入），请确保 server/ 目录下有 __init__.py
from .db import query, execute

# -----------------------------------------------------------------------------
# 工具函数
# -----------------------------------------------------------------------------

def _env(key: str, default: Optional[str] = None) -> str:
    """读取环境变量，给默认值。"""
    v = os.getenv(key)
    return v if v is not None else (default or "")

def _ok(data: Any = None, status: int = 200):
    """统一成功响应"""
    return jsonify({"ok": True, "data": data}), status

def _err(msg: str, status: int):
    """统一错误响应"""
    return jsonify({"ok": False, "error": msg}), status


# -----------------------------------------------------------------------------
# App 工厂
# -----------------------------------------------------------------------------

def create_app() -> Flask:
    """
    标准应用工厂：
    - 只在这里创建 app 实例
    - 注册扩展（CORS/JWT）
    - 注册蓝图（routes_images）
    - 注册认证路由（/api/auth/*）
    """
    # 允许 .env 覆盖环境（开发期友好）
    load_dotenv()

    app = Flask(__name__)

    # 统一配置（注意：让 routes_images.py 里手动解码与本文件签发一致）
    jwt_secret = _env("JWT_SECRET_KEY", _env("JWT_SECRET", "dev-secret"))
    app.config["JWT_SECRET_KEY"] = jwt_secret       # flask-jwt-extended 使用
    app.config["JWT_SECRET"] = jwt_secret           # routes_images 手动 decode 使用
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=3)  # 自行调整有效期

    # 文件/上传配置（供图片蓝图使用）
    app.config["UPLOAD_DIR"] = os.path.abspath(
        os.path.join(os.path.dirname(__file__), _env("UPLOAD_DIR", "uploads"))
    )
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 全局 50MB

    # CORS：仅放开 /api/*，前端本地开发会用到
    #CORS(app, resources={r"/api/*": {"origins": "*"}})
    CORS(app, resources={   r"/api/*": {"origins": "*"},   r"/files/*": {"origins": "*"}})

    # 注册 JWT
    jwt = JWTManager(app)  # noqa: F841

    # -------------------------------------------------------------------------
    # 认证相关 API
    # -------------------------------------------------------------------------

    def _user_public(row: Dict[str, Any]) -> Dict[str, Any]:
        """筛出可返回给前端的用户信息"""
        if not row:
            return {}
        return {
            "id": row["id"],
            "email": row.get("email"),
            "username": row.get("username"),
            "avatar_url": row.get("avatar_url"),
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        }

    def _get_user_by_identifier(identifier: str) -> Optional[Dict[str, Any]]:
        """
        支持邮箱或用户名登录：
        前端传入 identifier；这里先按邮箱查，再按用户名查
        """
        rows = query(
            "SELECT id,email,username,password_hash,avatar_url,created_at "
            "FROM users WHERE email=%s LIMIT 1",
            (identifier,)
        )
        if rows:
            return rows[0]
        rows = query(
            "SELECT id,email,username,password_hash,avatar_url,created_at "
            "FROM users WHERE username=%s LIMIT 1",
            (identifier,)
        )
        return rows[0] if rows else None

    @app.get("/api/health")
    def health():
        return _ok({"status": "ok"})

    @app.post("/api/auth/register")
    def register():
        """
        注册：email, username, password
        - 检查重复
        - 存储 password_hash
        - 可选：avatar_url
        """
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip()
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""

        if not email or not username or not password:
            return _err("缺少必要字段", 400)
        if len(password) < 6:
            return _err("密码至少 6 位", 400)

        # 重复检测
        dup = query("SELECT id FROM users WHERE email=%s OR username=%s LIMIT 1", (email, username))
        if dup:
            return _err("邮箱或用户名已存在", 409)

        pwd_hash = generate_password_hash(password)
        uid = execute(
            "INSERT INTO users (email, username, password_hash, created_at) "
            "VALUES (%s, %s, %s, NOW())",
            (email, username, pwd_hash)
        )

        user = query(
            "SELECT id,email,username,avatar_url,created_at FROM users WHERE id=%s",
            (uid,)
        )[0]
        return _ok(_user_public(user), 201)

    @app.post("/api/auth/login")
    def login():
        data = request.get_json(silent=True)
        if not data:
            # 表单或 multipart
            data = request.form.to_dict() or {}
            if not data and request.data:
                # 有些客户端没设 content-type，但发了原始 JSON
                try:
                    import json as _json
                    data = _json.loads(request.data.decode("utf-8"))
                except Exception:
                    data = {}

        # 2) 兼容多种键名：identifier / email / username
        raw_identifier = (
            data.get("identifier")
            or data.get("email")
            or data.get("username")
            or ""
        )
        identifier = raw_identifier.strip() if isinstance(raw_identifier, str) else ""
        password = (
            data.get("password")
            or data.get("passwd")
            or data.get("pwd")
            or ""
        )

        if not identifier or not password:
            return _err("缺少必要字段", 400)

        user = _get_user_by_identifier(identifier)
        if not user:
            return _err("用户不存在或密码错误", 401)

        from werkzeug.security import check_password_hash
        if not check_password_hash(user["password_hash"], password):
            return _err("用户不存在或密码错误", 401)

        token = create_access_token(identity=str(user["id"]))
        #return jsonify({"ok": True, "data": {"access_token": token, "user": _user_public(user)}})
        return jsonify(user=_user_public(user), access_token=token), 200

    @app.get("/api/auth/me")
    @jwt_required()
    def me():
        """校验 token，并返回当前用户信息"""
        uid = get_jwt_identity()
        rows = query(
            "SELECT id,email,username,avatar_url,created_at FROM users WHERE id=%s LIMIT 1",
            (uid,)
        )
        if not rows:
            return _err("用户不存在", 404)
        return _ok(_user_public(rows[0]))

    # -------------------------------------------------------------------------
    # 图片蓝图（上传/列表/标签/静态文件）
    # 注：使用相对导入，保持包内解析稳定
    # -------------------------------------------------------------------------
    from .routes_images import bp as images_bp
    from .routes_ai import bp as ai_bp
    app.register_blueprint(images_bp)
    app.register_blueprint(ai_bp)

    return app


# -----------------------------------------------------------------------------
# 允许：python -m server.app 启动
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # 推荐从“项目根目录”执行：python -m server.app
    # 如果需要更改端口或绑定地址，可改这里：
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)

