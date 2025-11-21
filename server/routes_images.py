# routes_images.py — 上传/列表/标签
import os, hashlib, time, json
from flask import Blueprint, request, jsonify, current_app, send_from_directory, g
from datetime import datetime
from server.db import query, execute, executemany
from server.util_exif import extract_exif
import jwt
from .db import query, execute, executemany
from .util_exif import extract_exif
from flask_jwt_extended import jwt_required, get_jwt_identity

bp = Blueprint("images", __name__)

ALLOWED_EXTS = {"jpg","jpeg","png","gif","webp","heic","heif"}  #advise 扩展支持 HEIC/HEIF
ALLOWED_MIMES = {"image/jpeg","image/png","image/gif","image/webp","image/heic","image/heif"}  #advise 对应 MIME

# ===== 简易鉴权（沿用你现有 JWT 配置） =====
'''
def current_user_id():
    """
    从 Authorization: Bearer <token> 中取出 user_id（与你 login 时签发的一致）
    """
    auth = request.headers.get("Authorization","")
    if not auth.startswith("Bearer "): return None
    token = auth.split(" ",1)[1].strip()
    try:
        payload = jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
        return int(payload["user_id"])
    except Exception:
        return None
'''
'''
def login_required(fn):
    def wrapper(*args, **kwargs):
        uid = current_user_id()
        if not uid:
            return jsonify({"error":"Unauthorized"}), 401
        g.user_id = uid
        return fn(*args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper
'''
def _current_user_id_from_jwt():
    """兼容 identity 既可能是数字也可能是 dict 的情况"""
    uid = get_jwt_identity()
    if isinstance(uid, dict):
        return uid.get("user_id") or uid.get("id")
    if isinstance(uid, str) and uid.isdigit():
       return int(uid)
    return uid


# ===== 静态文件回显（/files/<path>）=====
@bp.get("/files/<path:subpath>")
def serve_file(subpath):
    root = os.path.abspath(current_app.config["UPLOAD_DIR"])
    return send_from_directory(root, subpath)

# ===== 上传 =====
##@bp.post("/api/upload")
#@login_required
@bp.post("/api/upload")
@jwt_required()
def upload():
   # files = request.files.getlist("files")
    title = request.form.get("title") or None
    g.user_id = _current_user_id_from_jwt()
    files = request.files.getlist("files")
    desc  = request.form.get("description") or None
    tags  = request.form.get("tags")
    user_tags = []
    try:
        if tags:
            user_tags = list(filter(None, json.loads(tags)))
    except Exception:
        pass

    if not files:
        return jsonify({"error":"请选择要上传的文件"}), 400

    max_mb = int(os.getenv("MAX_UPLOAD_MB","10"))
    saved = []

    for fs in files:
        ext = (fs.filename.rsplit(".",1)[-1] or "").lower()
        if ext not in ALLOWED_EXTS or fs.mimetype not in ALLOWED_MIMES:
            return jsonify({"error": f"不支持的文件类型: {fs.mimetype}"}), 400
        fs.seek(0, os.SEEK_END)
        size = fs.tell()
        fs.seek(0)
        if size > max_mb * 1024 * 1024:
            return jsonify({"error": f"单个文件不能超过 {max_mb}MB"}), 400

        # 读取内容（10MB级，安全），计算 sha256
        content = fs.read()
        sha256 = hashlib.sha256(content).hexdigest()
        fs.seek(0)

        # 去重（同用户，同哈希）
        # 去重（同用户，同哈希）
        # 如果已经有记录了，我们不再新建 images 行，但会顺便补一份 EXIF（兼容老图片）
        # 去重（同用户，同哈希）
        # 这里一定要把 stored_path 和 path 都查出来，下面才能取到
        exists = query(
            "SELECT id, stored_path, path FROM images WHERE owner_id=%s AND sha256=%s LIMIT 1",
            (g.user_id, sha256)
        )
        #advise 不再跳过重复文件，强制继续入库（如需启用去重可改回 if exists）
        if  exists:
            row = exists[0]
            # 有 stored_path 用 stored_path，没有就退回到 path，防止 KeyError
            rel_path = (row.get("stored_path") or row.get("path") or "").strip()

            # （可选）如果想给旧图片补 EXIF，可以在这里加一小段：
            # 检查 exif 表是否已有记录，没有的话就用磁盘上的旧文件重跑一遍 EXIF 解析。
            exif_row = query("SELECT image_id FROM exif WHERE image_id=%s LIMIT 1", (row["id"],))
            if not exif_row and rel_path:
                abs_path_existing = os.path.join(current_app.config["UPLOAD_DIR"], rel_path)
                meta_dup = extract_exif(abs_path_existing)

                extra_json_dup = None
                if meta_dup.get("extra") is not None:
                    try:
                        extra_json_dup = json.dumps(meta_dup["extra"], ensure_ascii=False)
                    except TypeError:
                        extra_json_dup = json.dumps(str(meta_dup["extra"]), ensure_ascii=False)

                execute("""
                    INSERT INTO exif
                      (image_id, camera_make, camera_model,
                       f_number, exposure_time, iso, focal_length,
                       taken_at, gps_lat, gps_lng, extra)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      camera_make=VALUES(camera_make),
                      camera_model=VALUES(camera_model),
                      f_number=VALUES(f_number),
                      exposure_time=VALUES(exposure_time),
                      iso=VALUES(iso),
                      focal_length=VALUES(focal_length),
                      taken_at=VALUES(taken_at),
                      gps_lat=VALUES(gps_lat),
                      gps_lng=VALUES(gps_lng),
                      extra=VALUES(extra)
                """, (
                    row["id"],
                    meta_dup.get("camera_make"),
                    meta_dup.get("camera_model"),
                    meta_dup.get("f_number"),
                    meta_dup.get("exposure_time"),
                    meta_dup.get("iso"),
                    meta_dup.get("focal_length"),
                    meta_dup.get("taken_at"),
                    meta_dup.get("gps_lat"),
                    meta_dup.get("gps_lng"),
                    extra_json_dup,
                ))

            # 返回“重复上传”的信息
            saved.append({"duplicated": True, "image_id": row["id"]})
            continue

        # 计算保存路径：uploads/<uid>/<YYYYMM>/<timestamp_uuid>.<ext>
        subdir = f"{g.user_id}/{time.strftime('%Y%m')}"
        abs_dir = os.path.join(current_app.config["UPLOAD_DIR"], subdir)
        os.makedirs(abs_dir, exist_ok=True)
        fname   = f"{int(time.time()*1000)}_{hashlib.md5(content).hexdigest()[:8]}.{ext}"
        abs_path = os.path.join(abs_dir, fname)
        rel_path = f"{subdir}/{fname}"
        fs.save(abs_path)

        # 提取 EXIF（尺寸、拍摄时间、设备、GPS 等）+ 自动标签
        meta = extract_exif(abs_path)

        # 入库 images
        # 同时写 path 与 stored_path，兼容旧表结构
        image_id = execute("""
            INSERT INTO images
            (owner_id, path, stored_path, mime_type, size_bytes, width, height, sha256,
             camera_make, camera_model, gps_lat, gps_lng, taken_at, title, description, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """, (g.user_id, rel_path, rel_path, fs.mimetype, size, meta["width"], meta["height"], sha256,
              meta["camera_make"], meta["camera_model"], meta["gps_lat"], meta["gps_lng"],
              meta["taken_at"].strftime("%Y-%m-%d %H:%M:%S") if meta["taken_at"] else None,
              title, desc))
        



        # 写入 / 更新 exif 表（image_id 维度，一图一条）
        # 注意：exif.image_id 是主键，所以用 ON DUPLICATE KEY UPDATE 保证幂等
        extra_json = None
        if meta.get("extra") is not None:
            try:
                extra_json = json.dumps(meta["extra"], ensure_ascii=False)
            except TypeError:
                # 如果里面有不能序列化的东西，兜底用 str
                extra_json = json.dumps(str(meta["extra"]), ensure_ascii=False)

        execute("""
            INSERT INTO exif
              (image_id, camera_make, camera_model,
               f_number, exposure_time, iso, focal_length,
               taken_at, gps_lat, gps_lng, extra)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              camera_make=VALUES(camera_make),
              camera_model=VALUES(camera_model),
              f_number=VALUES(f_number),
              exposure_time=VALUES(exposure_time),
              iso=VALUES(iso),
              focal_length=VALUES(focal_length),
              taken_at=VALUES(taken_at),
              gps_lat=VALUES(gps_lat),
              gps_lng=VALUES(gps_lng),
              extra=VALUES(extra)
        """, (
            image_id,
            meta.get("camera_make"),
            meta.get("camera_model"),
            meta.get("f_number"),
            meta.get("exposure_time"),
            meta.get("iso"),
            meta.get("focal_length"),
            meta.get("taken_at"),
            meta.get("gps_lat"),
            meta.get("gps_lng"),
            extra_json,
        ))



        # 处理标签（用户标签 + 自动标签），写 tags / image_tags
        all_names = list(dict.fromkeys([*(user_tags or []), *meta["auto_tags"]]))  # 去重保序
        tag_ids = []





        for name in all_names:
            row = query("SELECT id FROM tags WHERE owner_id=%s AND name=%s LIMIT 1", (g.user_id, name))
            if row:
                tag_ids.append(row[0]["id"])
            else:
                tag_ids.append(execute(
                    "INSERT INTO tags (owner_id,name,kind) VALUES (%s,%s,%s)",
                    (g.user_id, name, 'exif' if name.startswith(("时间:","分辨率:","设备:","地点:")) else 'user')
                ))
        if tag_ids:
            executemany("INSERT IGNORE INTO image_tags (image_id,tag_id) VALUES (%s,%s)",
                        [(image_id, tid) for tid in tag_ids])

        saved.append({"image_id": image_id, "url": f"/files/{rel_path}"})

    return jsonify({"ok": True, "saved": saved})
    

# ===== 图片列表（用于首页瀑布流）=====
@bp.get("/api/images")
@jwt_required()
def list_images():
    g.user_id = _current_user_id_from_jwt()
    limit  = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    tag    = request.args.get("tag")  # 可选：按标签过滤

    if tag:
        # 先取标签ID，再关联
        rows = query("""
          SELECT i.id,i.title,i.stored_path,COALESCE(i.size_bytes, i.size) AS size_bytes,i.taken_at,i.created_at
          FROM images i
          JOIN image_tags it ON it.image_id = i.id
          JOIN tags t ON t.id = it.tag_id
          WHERE i.owner_id=%s AND t.name=%s
          ORDER BY COALESCE(i.taken_at,i.created_at) DESC
          LIMIT %s OFFSET %s
        """, (g.user_id, tag, limit, offset))
    else:
        rows = query("""
          SELECT i.id,i.title,i.stored_path,COALESCE(i.size_bytes, i.size) AS size_bytes,i.taken_at,i.created_at
          FROM images i
          WHERE i.owner_id=%s
          ORDER BY COALESCE(i.taken_at,i.created_at) DESC
          LIMIT %s OFFSET %s
        """, (g.user_id, limit, offset))

    if not rows:
        return jsonify({"items": []})

    ids = [r["id"] for r in rows]
    tag_rows = query("""
      SELECT it.image_id, t.name
      FROM image_tags it JOIN tags t ON t.id=it.tag_id
      WHERE it.image_id IN ({})
    """.format(",".join(["%s"]*len(ids))), ids)

    tags_map = {}
    for tr in tag_rows:
        tags_map.setdefault(tr["image_id"], []).append(tr["name"])

    def fmt(r):
        taken = r["taken_at"].strftime("%Y-%m-%d") if r["taken_at"] else r["created_at"].strftime("%Y-%m-%d")
        size_mb = round((r["size_bytes"] or 0)/1024/1024, 1)
        return {
            "id": r["id"],
            "title": r["title"] or "未命名",
            "tags": tags_map.get(r["id"], []),
            "date": taken,
            "sizeMB": size_mb,
            "url": f"/files/{r['stored_path']}"
        }
    return jsonify({"items": [fmt(r) for r in rows]})

#advise ????????????????/EXIF/??????????
@bp.get("/api/images/<int:image_id>")
@jwt_required()
def image_detail(image_id: int):
    g.user_id = _current_user_id_from_jwt()
    row = query(
        """
        SELECT i.id, i.title, i.description, i.stored_path, i.path,
               i.mime_type, COALESCE(i.size_bytes, i.size) AS size_bytes,
               i.width, i.height, i.created_at, i.taken_at,
               e.camera_make, e.camera_model, e.f_number, e.exposure_time,
               e.iso, e.focal_length, e.gps_lat, e.gps_lng, e.taken_at AS exif_taken_at
        FROM images i
        LEFT JOIN exif e ON e.image_id = i.id
        WHERE i.id=%s AND i.owner_id=%s
        LIMIT 1
        """,
        (image_id, g.user_id or 0)
    )
    if not row:
        return jsonify({"error": "??????"}), 404
    img = row[0]

    tag_rows = query(
        """
        SELECT t.name FROM image_tags it
        JOIN tags t ON t.id = it.tag_id
        WHERE it.image_id=%s
        ORDER BY t.name
        """,
        (image_id,)
    )
    tags = [t["name"] for t in tag_rows]

    rel_path = (img.get("stored_path") or img.get("path") or "").strip()
    url = f"/files/{rel_path}" if rel_path else ""

    exif = {
        "camera": img.get("camera_model") or img.get("camera_make"),
        "lens": None,  # ?????????????
        "focal": img.get("focal_length"),
        "aperture": f"f/{img['f_number']}" if img.get("f_number") else None,
        "shutter": img.get("exposure_time"),
        "iso": img.get("iso"),
        "takenAt": (img.get("exif_taken_at") or img.get("taken_at")),
        "gps": f"{img['gps_lat']},{img['gps_lng']}" if img.get("gps_lat") is not None and img.get("gps_lng") is not None else None,
    }

    #advise 派生关系：暂无真实链路，先用当前图片作为父占位，确保有缩略图
    relations = {
        "parent": {"title": img.get("title") or "原始图片", "thumb": url} if url else None,
        "children": [],  # 未来有子图时填充
    }

    resp = {
        "id": img["id"],
        "title": img.get("title"),
        "description": img.get("description"),
        "url": url,
        "width": img.get("width"),
        "height": img.get("height"),
        "sizeMB": round((img.get("size_bytes") or 0)/1024/1024, 1) if img.get("size_bytes") is not None else None,
        "format": (img.get("mime_type") or "").split("/")[-1].upper() if img.get("mime_type") else None,
        "createdAt": img.get("created_at").strftime("%Y-%m-%d %H:%M:%S") if img.get("created_at") else None,
        "takenAt": img.get("taken_at").strftime("%Y-%m-%d %H:%M:%S") if img.get("taken_at") else None,
        "tags": tags,
        "exif": exif,
        "relations": relations,
    }
    return jsonify(resp)


# ===== 标签列表（左侧筛选 & 上传弹窗选项）=====
@bp.get("/api/tags")
@jwt_required()
def list_tags():
    g.user_id = _current_user_id_from_jwt()
    rows = query("SELECT name FROM tags WHERE owner_id=%s ORDER BY name", (g.user_id,))
    return jsonify([r["name"] for r in rows])
