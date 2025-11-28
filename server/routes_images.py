# routes_images.py 上传/列表/标签
import hashlib
import json
import os
import time
from datetime import datetime
from io import BytesIO

from flask import Blueprint, current_app, g, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt_identity, jwt_required
from PIL import Image, ImageEnhance, ImageOps  # 简单图像处理

from server.db import execute, executemany, query
from server.util_exif import extract_exif

import jwt

bp = Blueprint("images", __name__)

ALLOWED_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif"}  # 支持 HEIC/HEIF
ALLOWED_MIMES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/heic",
    "image/heif",
}

# ===== 简易鉴权（沿用当前 JWT 配置）=====
'''
def current_user_id():
    """
    从 Authorization: Bearer <token> 中取 user_id（与 login 时签发的一致）
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
@bp.post("/api/upload")
@jwt_required()
def upload():
    title = request.form.get("title") or None
    g.user_id = _current_user_id_from_jwt()
    files = request.files.getlist("files")
    desc = request.form.get("description") or None
    tags = request.form.get("tags")
    user_tags = []
    try:
        if tags:
            user_tags = list(filter(None, json.loads(tags)))
    except Exception:
        pass

    if not files:
        return jsonify({"error": "请选择要上传的文件"}), 400

    max_mb = int(os.getenv("MAX_UPLOAD_MB", "10"))
    saved = []

    for fs in files:
        ext = (fs.filename.rsplit(".", 1)[-1] or "").lower()
        if ext not in ALLOWED_EXTS or fs.mimetype not in ALLOWED_MIMES:
            return jsonify({"error": f"不支持的文件类型: {fs.mimetype}"}), 400
        fs.seek(0, os.SEEK_END)
        size = fs.tell()
        fs.seek(0)
        if size > max_mb * 1024 * 1024:
            return jsonify({"error": f"单个文件不能超过 {max_mb}MB"}), 400

        # 读取内容（单个文件 10MB 级，安全），计算 sha256
        content = fs.read()
        sha256 = hashlib.sha256(content).hexdigest()
        fs.seek(0)

        # 去重（同用户，同哈希）；如果已有记录，直接返回重复信息
        exists = query(
            "SELECT id, stored_path, path FROM images WHERE owner_id=%s AND sha256=%s LIMIT 1",
            (g.user_id, sha256),
        )
        if exists:
            row = exists[0]
            rel_path = (row.get("stored_path") or row.get("path") or "").strip()

            # 如果旧图片缺少 EXIF，这里补录一次
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

                execute(
                    """
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
                """,
                    (
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
                    ),
                )

            saved.append({"duplicated": True, "image_id": row["id"]})
            continue

        # 计算保存路径：uploads/<uid>/<YYYYMM>/<timestamp_uuid>.<ext>
        subdir = f"{g.user_id}/{time.strftime('%Y%m')}"
        abs_dir = os.path.join(current_app.config["UPLOAD_DIR"], subdir)
        os.makedirs(abs_dir, exist_ok=True)
        fname = f"{int(time.time()*1000)}_{hashlib.md5(content).hexdigest()[:8]}.{ext}"
        abs_path = os.path.join(abs_dir, fname)
        rel_path = f"{subdir}/{fname}"
        fs.save(abs_path)

        # 提取 EXIF（尺寸、拍摄时间、设备、GPS 等）+ 自动标签
        meta = extract_exif(abs_path)

        # 入库 images，同时写入 path / stored_path
        image_id = execute(
            """
            INSERT INTO images
            (owner_id, path, stored_path, mime_type, size_bytes, width, height, sha256,
             camera_make, camera_model, gps_lat, gps_lng, taken_at, title, description, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """,
            (
                g.user_id,
                rel_path,
                rel_path,
                fs.mimetype,
                size,
                meta["width"],
                meta["height"],
                sha256,
                meta["camera_make"],
                meta["camera_model"],
                meta["gps_lat"],
                meta["gps_lng"],
                meta["taken_at"].strftime("%Y-%m-%d %H:%M:%S") if meta["taken_at"] else None,
                title,
                desc,
            ),
        )

        # 写入 / 更新 exif 表（image_id 维度，一图一条）
        extra_json = None
        if meta.get("extra") is not None:
            try:
                extra_json = json.dumps(meta["extra"], ensure_ascii=False)
            except TypeError:
                extra_json = json.dumps(str(meta["extra"]), ensure_ascii=False)

        execute(
            """
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
        """,
            (
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
            ),
        )

        # 处理标签（用户标签 + 自动标签），写入 tags / image_tags
        all_names = list(dict.fromkeys([*(user_tags or []), *meta["auto_tags"]]))  # 去重保序
        tag_ids = []

        for name in all_names:
            row = query("SELECT id FROM tags WHERE owner_id=%s AND name=%s LIMIT 1", (g.user_id, name))
            if row:
                tag_ids.append(row[0]["id"])
            else:
                tag_ids.append(
                    execute(
                        "INSERT INTO tags (owner_id,name,kind) VALUES (%s,%s,%s)",
                        (g.user_id, name, "exif" if name.startswith(("时间:", "分辨率", "设备:", "地点:")) else "user"),
                    )
                )
        if tag_ids:
            executemany(
                "INSERT IGNORE INTO image_tags (image_id,tag_id) VALUES (%s,%s)",
                [(image_id, tid) for tid in tag_ids],
            )

        saved.append({"image_id": image_id, "url": f"/files/{rel_path}"})

    return jsonify({"ok": True, "saved": saved})


# ===== 图片列表（用于首页瀑布流）=====
@bp.get("/api/images")
@jwt_required()
def list_images():
    g.user_id = _current_user_id_from_jwt()
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    tag = request.args.get("tag")  # 可选：按标签过滤

    if tag:
        rows = query(
            """
          SELECT i.id,i.title,i.stored_path,COALESCE(i.size_bytes, i.size) AS size_bytes,i.taken_at,i.created_at
          FROM images i
          JOIN image_tags it ON it.image_id = i.id
          JOIN tags t ON t.id = it.tag_id
          WHERE i.owner_id=%s AND t.name=%s
          ORDER BY COALESCE(i.taken_at,i.created_at) DESC
          LIMIT %s OFFSET %s
        """,
            (g.user_id, tag, limit, offset),
        )
    else:
        rows = query(
            """
          SELECT i.id,i.title,i.stored_path,COALESCE(i.size_bytes, i.size) AS size_bytes,i.taken_at,i.created_at
          FROM images i
          WHERE i.owner_id=%s
          ORDER BY COALESCE(i.taken_at,i.created_at) DESC
          LIMIT %s OFFSET %s
        """,
            (g.user_id, limit, offset),
        )

    if not rows:
        return jsonify({"items": []})

    ids = [r["id"] for r in rows]
    tag_rows = query(
        """
      SELECT it.image_id, t.name
      FROM image_tags it JOIN tags t ON t.id=it.tag_id
      WHERE it.image_id IN ({})
    """.format(
            ",".join(["%s"] * len(ids))
        ),
        ids,
    )

    tags_map = {}
    for tr in tag_rows:
        tags_map.setdefault(tr["image_id"], []).append(tr["name"])

    def fmt(r):
        taken = r["taken_at"].strftime("%Y-%m-%d") if r["taken_at"] else r["created_at"].strftime("%Y-%m-%d")
        size_mb = round((r["size_bytes"] or 0) / 1024 / 1024, 1)
        return {
            "id": r["id"],
            "title": r["title"] or "未命名",
            "tags": tags_map.get(r["id"], []),
            "date": taken,
            "sizeMB": size_mb,
            "url": f"/files/{r['stored_path']}",
        }

    return jsonify({"items": [fmt(r) for r in rows]})


# 详细信息：基础信息/EXIF/标签/派生关系
@bp.get("/api/images/<int:image_id>")
@jwt_required()
def image_detail(image_id: int):
    g.user_id = _current_user_id_from_jwt()
    row = query(
        """
        SELECT i.id, i.title, i.description, i.stored_path, i.path, i.parent_id,
               i.mime_type, COALESCE(i.size_bytes, i.size) AS size_bytes,
               i.width, i.height, i.created_at, i.taken_at,
               e.camera_make, e.camera_model, e.f_number, e.exposure_time,
               e.iso, e.focal_length, e.gps_lat, e.gps_lng, e.taken_at AS exif_taken_at
        FROM images i
        LEFT JOIN exif e ON e.image_id = i.id
        WHERE i.id=%s AND i.owner_id=%s
        LIMIT 1
        """,
        (image_id, g.user_id or 0),
    )
    if not row:
        return jsonify({"error": "图片不存在或无权限"}), 404
    img = row[0]

    tag_rows = query(
        """
        SELECT t.name FROM image_tags it
        JOIN tags t ON t.id = it.tag_id
        WHERE it.image_id=%s
        ORDER BY t.name
        """,
        (image_id,),
    )
    tags = [t["name"] for t in tag_rows]

    rel_path = (img.get("stored_path") or img.get("path") or "").strip()
    url = f"/files/{rel_path}" if rel_path else ""

    exif = {
        "camera": img.get("camera_model") or img.get("camera_make"),
        "lens": None,  # 未单独存镜头信息
        "focal": img.get("focal_length"),
        "aperture": f"f/{img['f_number']}" if img.get("f_number") else None,
        "shutter": img.get("exposure_time"),
        "iso": img.get("iso"),
        "takenAt": (img.get("exif_taken_at") or img.get("taken_at")),
        "gps": f"{img['gps_lat']},{img['gps_lng']}"
        if img.get("gps_lat") is not None and img.get("gps_lng") is not None
        else None,
    }

    # 派生关系：返回 parent 和 children 列表
    parent = None
    if img.get("parent_id"):
        prow = query("SELECT id,title,stored_path,path FROM images WHERE id=%s LIMIT 1", (img["parent_id"],))
        if prow:
            p = prow[0]
            p_rel = (p.get("stored_path") or p.get("path") or "").strip()
            parent = {"id": p["id"], "title": p.get("title") or "原始图片", "thumb": f"/files/{p_rel}" if p_rel else ""}

    child_rows = query(
        "SELECT id,title,stored_path,path FROM images WHERE parent_id=%s ORDER BY created_at DESC LIMIT 50",
        (image_id,),
    )
    children = []
    for c in child_rows:
        c_rel = (c.get("stored_path") or c.get("path") or "").strip()
        children.append({"id": c["id"], "title": c.get("title") or "派生图片", "thumb": f"/files/{c_rel}" if c_rel else ""})

    relations = {"parent": parent, "children": children}

    resp = {
        "id": img["id"],
        "title": img.get("title"),
        "description": img.get("description"),
        "url": url,
        "width": img.get("width"),
        "height": img.get("height"),
        "sizeMB": round((img.get("size_bytes") or 0) / 1024 / 1024, 1) if img.get("size_bytes") is not None else None,
        "format": (img.get("mime_type") or "").split("/")[-1].upper() if img.get("mime_type") else None,
        "createdAt": img.get("created_at").strftime("%Y-%m-%d %H:%M:%S") if img.get("created_at") else None,
        "takenAt": img.get("taken_at").strftime("%Y-%m-%d %H:%M:%S") if img.get("taken_at") else None,
        "tags": tags,
        "exif": exif,
        "relations": relations,
    }
    return jsonify(resp)


# 简易图像处理：裁剪、旋转、亮度/对比度/饱和度/色温/锐化/缩放
def _apply_edits(img: Image.Image, params: dict) -> Image.Image:
    # 1) 裁剪：安全取值防止越界
    crop_rect = params.get("crop_rect")
    if crop_rect and all(k in crop_rect for k in ("x", "y", "width", "height")):
        try:
            x = float(crop_rect["x"])
            y = float(crop_rect["y"])
            w = float(crop_rect["width"])
            h = float(crop_rect["height"])
            if w > 0 and h > 0:
                x2 = min(img.width, x + w)
                y2 = min(img.height, y + h)
                x = max(0, x)
                y = max(0, y)
                if x2 > x and y2 > y:
                    img = img.crop((x, y, x2, y2))
        except Exception:
            pass  # 裁剪异常时忽略

    # 2) 旋转
    deg = params.get("rotate") or 0
    try:
        deg_f = float(deg)
        if deg_f % 360 != 0:
            img = img.rotate(-deg_f, expand=True)  # PIL 顺时针需要取负角度
    except Exception:
        pass

    # 3) 亮度/对比度/饱和度/色温/锐化
    def _factor(val):
        try:
            return 1 + float(val) / 100
        except Exception:
            return 1

    b = _factor(params.get("brightness", 0))
    c = _factor(params.get("contrast", 0))
    s = _factor(params.get("saturation", 0))
    if b != 1:
        img = ImageEnhance.Brightness(img).enhance(b)
    if c != 1:
        img = ImageEnhance.Contrast(img).enhance(c)
    if s != 1:
        img = ImageEnhance.Color(img).enhance(s)

    warm = params.get("warmth", 0)
    try:
        warm_v = float(warm)
        if warm_v != 0 and img.mode == "RGB":
            r, g_, b_ = img.split()
            if warm_v > 0:
                r = ImageEnhance.Brightness(r).enhance(1 + warm_v / 200)
            else:
                b_ = ImageEnhance.Brightness(b_).enhance(1 + abs(warm_v) / 200)
            img = Image.merge("RGB", (r, g_, b_))
    except Exception:
        pass

    sharp = params.get("sharpen", 0)
    try:
        sharp_v = float(sharp)
        if sharp_v > 0:
            img = ImageEnhance.Sharpness(img).enhance(1 + sharp_v / 50)
    except Exception:
        pass

    # 4) 缩放：支持保持比例 keep_ratio 或目标尺寸
    tw = params.get("target_width")
    th = params.get("target_height")
    keep_ratio = params.get("keep_ratio", False)
    ratio_w = params.get("ratio_width")
    ratio_h = params.get("ratio_height")

    try:
        tw = int(tw) if tw not in (None, "", False) else None
        th = int(th) if th not in (None, "", False) else None
        ratio_w = float(ratio_w) if ratio_w not in (None, "", False) else None
        ratio_h = float(ratio_h) if ratio_h not in (None, "", False) else None
    except Exception:
        tw = th = ratio_w = ratio_h = None

    if tw or th:
        orig_w, orig_h = img.size
        target_ratio = (ratio_w / ratio_h) if (keep_ratio and ratio_w and ratio_h and ratio_h != 0) else (orig_w / orig_h)

        def _scale_for_bound(bound_w, bound_h):
            """在给定边界内求缩放比"""
            sw = bound_w / orig_w if bound_w else None
            sh = bound_h / orig_h if bound_h else None
            factors = [s for s in (sw, sh) if s]
            scale = min(factors) if factors else 1.0
            return max(scale, 0.01)

        if keep_ratio:
            bound_w = tw or (th * target_ratio if th else orig_w)
            bound_h = th or (tw / target_ratio if tw else orig_h)
            scale = _scale_for_bound(bound_w, bound_h)
            new_w = max(1, int(orig_w * scale))
            new_h = max(1, int(orig_h * scale))
        else:
            if tw and th:
                scale = _scale_for_bound(tw, th)
                new_w = max(1, int(orig_w * scale))
                new_h = max(1, int(orig_h * scale))
            elif tw:
                new_w = max(1, tw)
                new_h = max(1, int(orig_h * (new_w / orig_w)))
            elif th:
                new_h = max(1, th)
                new_w = max(1, int(orig_w * (new_h / orig_h)))
        try:
            img = img.resize((new_w, new_h), Image.LANCZOS)
        except Exception:
            pass  # 缩放异常时保持原图

    return img


# 裁剪/滤镜编辑接口：前端 POST /api/images/<id>/edit
@bp.post("/api/images/<int:image_id>/edit")
@jwt_required()
def edit_image(image_id: int):
    g.user_id = _current_user_id_from_jwt()
    data = request.get_json(silent=True) or {}
    mode = data.get("mode") or "override"
    export_name = (data.get("exportName") or "").strip()

    base_rows = query(
        "SELECT id,owner_id,title,stored_path,path,mime_type FROM images WHERE id=%s AND owner_id=%s LIMIT 1",
        (image_id, g.user_id or 0),
    )
    if not base_rows:
        return jsonify({"error": "图片不存在或无权限查看"}), 404
    base = base_rows[0]
    rel_path = (base.get("stored_path") or base.get("path") or "").strip()
    if not rel_path:
        return jsonify({"error": "原图路径缺失"}), 400

    abs_root = os.path.abspath(current_app.config["UPLOAD_DIR"])
    abs_in = os.path.join(abs_root, rel_path)
    if not os.path.exists(abs_in):
        return jsonify({"error": "原图文件不存在"}), 404

    try:
        with Image.open(abs_in) as img:
            img = img.convert("RGB")
            edited = _apply_edits(img, data)
            buf = BytesIO()
            ext = (os.path.splitext(rel_path)[-1] or ".jpg").lower()
            fmt = "JPEG" if ext in [".jpg", ".jpeg"] else ext.replace(".", "").upper() or "JPEG"
            edited.save(buf, format=fmt, quality=92)
            binary = buf.getvalue()
    except Exception as e:
        return jsonify({"error": f"处理图片失败: {e}"}), 500

    sha256 = hashlib.sha256(binary).hexdigest()
    size_bytes = len(binary)

    if mode == "override":
        abs_out = abs_in
        rel_out = rel_path
    else:
        subdir = f"{g.user_id}/{time.strftime('%Y%m')}"
        os.makedirs(os.path.join(abs_root, subdir), exist_ok=True)
        fname = f"{int(time.time()*1000)}_{hashlib.md5(binary).hexdigest()[:8]}{ext or '.jpg'}"
        abs_out = os.path.join(abs_root, subdir, fname)
        rel_out = f"{subdir}/{fname}"

    with open(abs_out, "wb") as f:
        f.write(binary)

    meta = extract_exif(abs_out)
    width = meta.get("width")
    height = meta.get("height")
    taken_at = meta.get("taken_at")

    if mode == "override":
        execute(
            """
            UPDATE images
            SET stored_path=%s, path=%s, mime_type=%s,
                size_bytes=%s, width=%s, height=%s, sha256=%s,
                taken_at=%s, updated_at=NOW(), title=COALESCE(%s,title)
            WHERE id=%s AND owner_id=%s
            """,
            (
                rel_out,
                rel_out,
                f"image/{fmt.lower()}",
                size_bytes,
                width,
                height,
                sha256,
                taken_at.strftime("%Y-%m-%d %H:%M:%S") if taken_at else None,
                export_name or None,
                image_id,
                g.user_id,
            ),
        )
        target_id = image_id
    else:
        target_id = execute(
            """
            INSERT INTO images
            (owner_id, parent_id, path, stored_path, mime_type, size_bytes, width, height, sha256,
             taken_at, title, description, created_at)
            SELECT owner_id, id, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s, description, NOW()
            FROM images WHERE id=%s AND owner_id=%s
            """,
            (
                rel_out,
                rel_out,
                f"image/{fmt.lower()}",
                size_bytes,
                width,
                height,
                sha256,
                taken_at.strftime("%Y-%m-%d %H:%M:%S") if taken_at else None,
                export_name or (base.get("title") or ""),
                image_id,
                g.user_id,
            ),
        )
        tag_ids = query("SELECT tag_id FROM image_tags WHERE image_id=%s", (image_id,))
        if tag_ids:
            executemany(
                "INSERT IGNORE INTO image_tags (image_id,tag_id) VALUES (%s,%s)",
                [(target_id, t["tag_id"]) for t in tag_ids],
            )

    extra_json = None
    if meta.get("extra") is not None:
        try:
            extra_json = json.dumps(meta["extra"], ensure_ascii=False)
        except TypeError:
            extra_json = json.dumps(str(meta["extra"]), ensure_ascii=False)
    execute(
        """
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
        """,
        (
            target_id,
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
        ),
    )

    return jsonify({"ok": True, "image_id": target_id, "url": f"/files/{rel_out}", "mode": mode})


# ===== 标签列表（前端可用于筛选 & 上传时选择）=====
@bp.get("/api/tags")
@jwt_required()
def list_tags():
    g.user_id = _current_user_id_from_jwt()
    rows = query("SELECT name FROM tags WHERE owner_id=%s ORDER BY name", (g.user_id,))
    return jsonify([r["name"] for r in rows])
