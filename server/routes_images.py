# routes_images.py 上传/列表/标签
import hashlib
import json
import os
import re
import time
from datetime import datetime
from io import BytesIO
import zipfile  # #advise 批量打包下载
import tempfile

from flask import Blueprint, current_app, g, jsonify, request, send_file, send_from_directory
from flask_jwt_extended import get_jwt_identity, jwt_required
from PIL import Image, ImageEnhance, ImageFilter, ImageOps  # 简单图像处理

from server.db import execute, executemany, query
from server.photo_analysis_agent import analyze_image
from server.util_exif import extract_exif
from server.utils import classify_device

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
TMP_AI_DIR = os.path.join(tempfile.gettempdir(), "bs_ai_tmp")
os.makedirs(TMP_AI_DIR, exist_ok=True)


def _facet_from_sql(field_expr: str, owner_id: int, limit: int = 50):
    sql = f"""
        SELECT val AS value, COUNT(*) AS cnt FROM (
            SELECT TRIM({field_expr}) AS val
            FROM images i
            LEFT JOIN exif e ON e.image_id = i.id
            WHERE i.owner_id=%s AND {field_expr} IS NOT NULL AND TRIM({field_expr})!=''
        ) t
        GROUP BY val
        ORDER BY cnt DESC, val ASC
        LIMIT %s
    """
    rows = query(sql, (owner_id, limit))
    return [{"value": r["value"], "count": r["cnt"]} for r in rows]

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


_VISIBILITY_COLUMN = None


def _has_visibility_column() -> bool:
    global _VISIBILITY_COLUMN
    if _VISIBILITY_COLUMN is not None:
        return _VISIBILITY_COLUMN
    try:
        rows = query(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=DATABASE()
              AND TABLE_NAME='images'
              AND COLUMN_NAME='visibility'
            LIMIT 1
            """
        )
        _VISIBILITY_COLUMN = bool(rows)
    except Exception:
        _VISIBILITY_COLUMN = False
    return _VISIBILITY_COLUMN


# ===== 静态文件回显（/files/<path>）=====
@bp.get("/files/<path:subpath>")
def serve_file(subpath):
    root = os.path.abspath(current_app.config["UPLOAD_DIR"])
    return send_from_directory(root, subpath)


@bp.get("/api/images/facets")
@jwt_required()
def image_facets():
    """聚合建议：相机品牌/型号/格式/设备"""
    g.user_id = _current_user_id_from_jwt()
    try:
        facets = {
            "camera_make": _facet_from_sql("COALESCE(e.camera_make, i.camera_make)", g.user_id),
            "camera_model": _facet_from_sql("COALESCE(e.camera_model, i.camera_model)", g.user_id),
        }

        # 格式：从 stored_path/path/mime 取扩展名
        fmt_rows = query(
            """
            SELECT LOWER(SUBSTRING_INDEX(COALESCE(i.stored_path,i.path),'.',-1)) AS fmt, COUNT(*) AS cnt
            FROM images i
            WHERE i.owner_id=%s AND COALESCE(i.stored_path,i.path) IS NOT NULL
            GROUP BY fmt
            HAVING fmt IS NOT NULL AND fmt!=''
            ORDER BY cnt DESC, fmt ASC
            LIMIT 50
            """,
            (g.user_id,),
        )
        facets["format"] = [{"value": r["fmt"], "count": r["cnt"]} for r in fmt_rows if r.get("fmt")]

        # 设备：根据品牌/型号粗分
        dev_rows = query(
            """
            SELECT COALESCE(e.camera_make, i.camera_make) AS make, COALESCE(e.camera_model, i.camera_model) AS model
            FROM images i
            LEFT JOIN exif e ON e.image_id = i.id
            WHERE i.owner_id=%s
            """,
            (g.user_id,),
        )
        device_count = {}
        for r in dev_rows:
            dev = classify_device(r.get("make"), r.get("model"))
            if dev:
                device_count[dev] = device_count.get(dev, 0) + 1
        facets["device"] = [{"value": k, "count": v} for k, v in sorted(device_count.items(), key=lambda x: x[1], reverse=True)]

        return jsonify(facets)
    except Exception as exc:
        return jsonify({"ok": False, "error": "聚合失败", "detail": str(exc)}), 500


# ===== AI 智能分析 =====
@bp.post("/api/v1/images/ai-analyze")
@jwt_required()
def ai_analyze_image():
    """接收临时图片，调用 DashScope 进行自动描述与标签分析。"""
    g.user_id = _current_user_id_from_jwt()
    fs = request.files.get("file")
    if not fs:
        return jsonify({"ok": False, "error": "请先上传要分析的图片文件"}), 400

    ext = (fs.filename.rsplit(".", 1)[-1] or "").lower() if fs.filename else ""
    mime = (fs.mimetype or "").lower()
    if ext not in ALLOWED_EXTS or mime not in ALLOWED_MIMES:
        return jsonify({"ok": False, "error": "仅支持常见图片格式"}), 400

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix="ai_", suffix=f".{ext or 'jpg'}", dir=TMP_AI_DIR)
        os.close(fd)
        fs.save(temp_path)

        result = analyze_image(temp_path)
        tags_raw = result.get("tags") or []
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in re.split(r"[，,、\s]+", tags_raw) if t.strip()]
        elif isinstance(tags_raw, (list, tuple)):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        else:
            tags = []
        return jsonify(
            {
                "ok": True,
                "title": result.get("title") or "",
                "description": result.get("description") or "",
                "tags": tags,
            }
        )
    except Exception as exc:
        msg = str(exc) or "AI 分析失败"
        return jsonify({"ok": False, "error": msg}), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


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


@bp.get("/api/images/stats")
@jwt_required()
def image_stats():
    g.user_id = _current_user_id_from_jwt()
    try:
        rows = query(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN DATE(created_at)=CURDATE() THEN 1 ELSE 0 END) AS today
            FROM images
            WHERE owner_id=%s
            """,
            (g.user_id,),
        )
        row = rows[0] if rows else {}
        total = int(row.get("total") or 0)
        today = int(row.get("today") or 0)
        return jsonify({"total": total, "today": today})
    except Exception as exc:
        return jsonify({"error": "统计失败", "detail": str(exc)}), 500


@bp.get("/api/images/search")
@jwt_required()
def search_images():
    """高阶搜索：名称/描述模糊 + EXIF + 文件大小 + 多标签交集"""
    g.user_id = _current_user_id_from_jwt()
    args = request.args
    limit = int(args.get("limit", 50))
    offset = int(args.get("offset", 0))
    if limit > 200:
        limit = 200

    q = (args.get("q") or "").strip()
    date_start = (args.get("date_start") or "").strip()
    date_end = (args.get("date_end") or "").strip()
    fmt = (args.get("format") or "").strip().lower().lstrip(".")
    camera_make = (args.get("camera_make") or "").strip()
    camera_model = (args.get("camera_model") or "").strip()
    iso = (args.get("iso") or "").strip()
    focal_length = (args.get("focal_length") or "").strip()
    min_size = (args.get("min_size_mb") or "").strip()
    max_size = (args.get("max_size_mb") or "").strip()
    device_params = args.getlist("device") or []
    if not device_params and args.get("device"):
        device_params = [p.strip() for p in (args.get("device") or "").split(",") if p.strip()]
    min_size_kb = (args.get("min_size_kb") or "").strip()
    max_size_kb = (args.get("max_size_kb") or "").strip()

    tag_params = args.getlist("tags") or []
    if not tag_params and args.get("tags"):
        tag_params = [p.strip() for p in (args.get("tags") or "").split(",") if p.strip()]
    tag_params = [t for t in tag_params if t]

    conditions = ["i.owner_id=%s"]
    params = [g.user_id]
    joins = ["LEFT JOIN exif e ON e.image_id = i.id"]
    having = ""
    group_by = ""

    # 名称 / 描述模糊
    if q:
        like = f"%{q}%"
        conditions.append("(i.title LIKE %s OR i.description LIKE %s)")
        params.extend([like, like])

    # 时间范围（取拍摄时间/创建时间）
    ts_expr = "COALESCE(i.taken_at, i.created_at)"
    if date_start:
        conditions.append(f"{ts_expr} >= %s")
        params.append(date_start)
    if date_end:
        conditions.append(f"{ts_expr} <= %s")
        params.append(date_end)

    # 文件格式：扩展名或 mime
    if fmt:
        conditions.append(
            "(LOWER(SUBSTRING_INDEX(i.stored_path,'.',-1))=%s "
            "OR LOWER(SUBSTRING_INDEX(i.path,'.',-1))=%s "
            "OR LOWER(SUBSTRING_INDEX(i.mime_type,'/',-1))=%s)"
        )
        params.extend([fmt, fmt, fmt])

    # EXIF 维度
    if camera_make:
        conditions.append("COALESCE(e.camera_make, i.camera_make) LIKE %s")
        params.append(f"%{camera_make}%")
    if camera_model:
        conditions.append("COALESCE(e.camera_model, i.camera_model) LIKE %s")
        params.append(f"%{camera_model}%")
    if iso:
        try:
            iso_val = int(iso)
            conditions.append("e.iso = %s")
            params.append(iso_val)
        except Exception:
            pass
    if focal_length:
        conditions.append("e.focal_length = %s")
        params.append(focal_length)

    # 文件大小（MB）
    size_expr = "COALESCE(i.size_bytes, i.size) / 1024 / 1024.0"
    try:
        if min_size_kb:
            min_size_val = max(0.0, float(min_size_kb) / 1024.0)
            conditions.append(f"{size_expr} >= %s")
            params.append(min_size_val)
        elif min_size:
            min_size_val = max(0.0, float(min_size))
            conditions.append(f"{size_expr} >= %s")
            params.append(min_size_val)
    except Exception:
        pass
    try:
        if max_size_kb:
            max_size_val = min(float(max_size_kb) / 1024.0, 10.0)
            conditions.append(f"{size_expr} <= %s")
            params.append(max_size_val)
        elif max_size:
            max_size_val = min(float(max_size), 10.0)
            conditions.append(f"{size_expr} <= %s")
            params.append(max_size_val)
    except Exception:
        pass

    # 标签交集过滤
    if tag_params:
        joins.append("JOIN image_tags it ON it.image_id = i.id")
        joins.append("JOIN tags t ON t.id = it.tag_id")
        conditions.append("t.owner_id=%s")
        params.append(g.user_id)
        placeholders = ",".join(["%s"] * len(tag_params))
        conditions.append(f"t.name IN ({placeholders})")
        params.extend(tag_params)
        group_by = (
            "GROUP BY i.id, i.title, i.description, i.stored_path, i.path, "
            "i.size_bytes, i.size, i.taken_at, i.created_at, "
            "i.camera_make, i.camera_model, e.camera_make, e.camera_model, e.iso, e.focal_length"
        )
        having = "HAVING COUNT(DISTINCT t.name) >= %s"
        params.append(len(tag_params))

    where_sql = " AND ".join(conditions)
    sql = f"""
        SELECT
          i.id, i.title, i.description, i.stored_path, i.path,
          COALESCE(i.size_bytes, i.size) AS size_bytes,
          {ts_expr} AS sort_time,
          i.taken_at, i.created_at,
          COALESCE(e.camera_make, i.camera_make) AS camera_make,
          COALESCE(e.camera_model, i.camera_model) AS camera_model,
          e.iso, e.focal_length
        FROM images i
        {" ".join(joins)}
        WHERE {where_sql}
        {group_by}
        {having}
        ORDER BY sort_time DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    rows = query(sql, params)
    if not rows:
        return jsonify({"items": []})

    ids = [r["id"] for r in rows]
    tag_rows = query(
        """
        SELECT it.image_id, t.name
        FROM image_tags it
        JOIN tags t ON t.id = it.tag_id
        WHERE it.image_id IN ({})
        """.format(",".join(["%s"] * len(ids))),
        ids,
    )

    tags_map = {}
    for tr in tag_rows:
        tags_map.setdefault(tr["image_id"], []).append(tr["name"])

    def fmt_row(r):
        rel_path = (r.get("stored_path") or r.get("path") or "").strip()
        date_val = r.get("sort_time") or r.get("taken_at") or r.get("created_at")
        taken = date_val.strftime("%Y-%m-%d") if date_val else None
        size_mb = round((r.get("size_bytes") or 0) / 1024 / 1024, 2)
        device = classify_device(r.get("camera_make"), r.get("camera_model"))
        return {
            "id": r["id"],
            "title": r.get("title") or "未命名",
            "description": r.get("description"),
            "tags": tags_map.get(r["id"], []),
            "date": taken,
            "sizeMB": size_mb,
            "url": f"/files/{rel_path}" if rel_path else "",
            "device": device,
        }

    items = [fmt_row(r) for r in rows]
    if device_params:
        items = [it for it in items if it.get("device") and it["device"] in device_params]

    return jsonify({"items": items})


# ===== #advise 热门标签（含标签名/图片标题模糊）=====
@bp.get("/api/tags/popular")
@jwt_required()
def popular_tags():
    g.user_id = _current_user_id_from_jwt()
    kw = (request.args.get("q") or "").strip()
    params = [g.user_id, g.user_id]
    like_sql = ""
    if kw:
        like = f"%{kw}%"
        like_sql = " AND (t.name LIKE %s OR i.title LIKE %s)"
        params.extend([like, like])

    sql = f"""
        SELECT t.id, t.name, COUNT(DISTINCT it.image_id) AS image_count
        FROM tags t
        JOIN image_tags it ON it.tag_id = t.id
        JOIN images i ON i.id = it.image_id
        WHERE t.owner_id=%s AND i.owner_id=%s{like_sql}
        GROUP BY t.id, t.name
        ORDER BY image_count DESC, t.name ASC
        LIMIT 50
    """
    rows = query(sql, params)
    return jsonify([{"id": r["id"], "name": r["name"], "image_count": r["image_count"]} for r in rows])


# ===== AI 推荐标签采纳 =====
@bp.post("/api/images/<int:image_id>/tags/accept_suggestions")
@jwt_required()
def accept_suggested_tags(image_id: int):
    """将 AI 推荐标签写入现有 tags / image_tags 表。"""
    g.user_id = _current_user_id_from_jwt()
    data = request.get_json(silent=True) or {}
    tags = data.get("tags") or []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    if not tags:
        return jsonify({"error": "缺少 tags"}), 400

    img_rows = query("SELECT id FROM images WHERE id=%s AND owner_id=%s LIMIT 1", (image_id, g.user_id))
    if not img_rows:
        return jsonify({"error": "图片不存在或无权限"}), 404

    tag_ids = []
    for name in tags:
        existing = query("SELECT id FROM tags WHERE owner_id=%s AND name=%s LIMIT 1", (g.user_id, name))
        if existing:
            tag_ids.append(existing[0]["id"])
        else:
            tag_ids.append(execute("INSERT INTO tags (owner_id,name,kind) VALUES (%s,%s,%s)", (g.user_id, name, "user")))

    if tag_ids:
        pairs = [(image_id, tid) for tid in tag_ids]
        executemany("INSERT IGNORE INTO image_tags (image_id,tag_id) VALUES (%s,%s)", pairs)

    current = query(
        """
        SELECT t.name FROM image_tags it
        JOIN tags t ON t.id = it.tag_id
        WHERE it.image_id=%s
        ORDER BY t.name
        """,
        (image_id,),
    )
    return jsonify({"ok": True, "tags": [r["name"] for r in current]})


# ===== #advise 批量删除与批量加标签（仅操作数据，不改表结构）=====
@bp.post("/api/images/batch/delete")
@jwt_required()
def batch_delete_images():
    g.user_id = _current_user_id_from_jwt()
    data = request.get_json(silent=True) or {}
    ids = data.get("image_ids") or []
    try:
        ids = [int(x) for x in ids if str(x).isdigit()]
    except Exception:
        ids = []
    if not ids:
        return jsonify({"error": "缺少 image_ids"}), 400

    placeholders = ",".join(["%s"] * len(ids))
    valid_rows = query(
        f"SELECT id FROM images WHERE owner_id=%s AND id IN ({placeholders})",
        [g.user_id, *ids],
    )
    if not valid_rows:
        return jsonify({"ok": True, "deleted": 0})

    deleted = 0
    for r in valid_rows:
        execute("DELETE FROM images WHERE owner_id=%s AND id=%s", (g.user_id, r["id"]))
        deleted += 1
    return jsonify({"ok": True, "deleted": deleted})


@bp.post("/api/images/batch/add_tags")
@jwt_required()
def batch_add_tags():
    g.user_id = _current_user_id_from_jwt()
    data = request.get_json(silent=True) or {}
    ids = data.get("image_ids") or []
    tags = data.get("tags") or []
    try:
        ids = [int(x) for x in ids if str(x).isdigit()]
    except Exception:
        ids = []
    tags = [t.strip() for t in tags if t and str(t).strip()]
    if not ids or not tags:
        return jsonify({"error": "缺少 image_ids 或 tags"}), 400

    placeholders = ",".join(["%s"] * len(ids))
    valid_images = query(
        f"SELECT id FROM images WHERE owner_id=%s AND id IN ({placeholders})",
        [g.user_id, *ids],
    )
    if not valid_images:
        return jsonify({"error": "没有可操作的图片"}), 400

    # #advise 批量添加标签时，允许创建不存在的标签
    tag_rows = []
    for name in tags:
        existing = query("SELECT id FROM tags WHERE owner_id=%s AND name=%s LIMIT 1", (g.user_id, name))
        if existing:
            tag_rows.append({"id": existing[0]["id"], "name": name})
        else:
            tid = execute("INSERT INTO tags (owner_id,name,kind) VALUES (%s,%s,%s)", (g.user_id, name, "user"))
            tag_rows.append({"id": tid, "name": name})

    pairs = []
    for img in valid_images:
        for t in tag_rows:
            pairs.append((img["id"], t["id"]))
    if pairs:
        executemany("INSERT IGNORE INTO image_tags (image_id,tag_id) VALUES (%s,%s)", pairs)
    return jsonify({"ok": True, "added": len(pairs)})


# ===== #advise 单图删除与批量下载 =====
@bp.delete("/api/images/<int:image_id>")
@jwt_required()
def delete_image(image_id: int):
    g.user_id = _current_user_id_from_jwt()
    rows = query("SELECT id, stored_path, path FROM images WHERE id=%s AND owner_id=%s LIMIT 1", (image_id, g.user_id))
    if not rows:
        return jsonify({"error": "图片不存在或无权限"}), 404
    rel_path = (rows[0].get("stored_path") or rows[0].get("path") or "").strip()

    execute("DELETE FROM images WHERE id=%s AND owner_id=%s", (image_id, g.user_id))

    # 删除物理文件（存在则删除，不阻塞主流程）
    if rel_path:
        abs_root = os.path.abspath(current_app.config["UPLOAD_DIR"])
        abs_path = os.path.join(abs_root, rel_path)
        try:
            if os.path.exists(abs_path):
                os.remove(abs_path)
        except Exception:
            pass

    return jsonify({"ok": True, "deleted": image_id})


@bp.post("/api/images/batch/download")
@jwt_required()
def batch_download_images():
    """批量下载：打包选中图片为 ZIP 返回"""
    g.user_id = _current_user_id_from_jwt()
    data = request.get_json(silent=True) or {}
    ids = data.get("image_ids") or []
    try:
        ids = [int(x) for x in ids if str(x).isdigit()]
    except Exception:
        ids = []
    if not ids:
        return jsonify({"error": "缺少 image_ids"}), 400

    placeholders = ",".join(["%s"] * len(ids))
    rows = query(
        f"""
        SELECT id, title, stored_path, path
        FROM images
        WHERE owner_id=%s AND id IN ({placeholders})
        """,
        [g.user_id, *ids],
    )
    if not rows:
        return jsonify({"error": "没有可下载的图片"}), 400

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        root = os.path.abspath(current_app.config["UPLOAD_DIR"])
        for r in rows:
            rel = (r.get("stored_path") or r.get("path") or "").strip()
            if not rel:
                continue
            abs_path = os.path.join(root, rel)
            if not os.path.exists(abs_path):
                continue
            base = os.path.basename(rel) or f"image_{r['id']}"
            # 使用 id 前缀避免重名
            arcname = f"{r['id']}_{base}"
            try:
                zf.write(abs_path, arcname=arcname)
            except Exception:
                continue
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="private-picture-shop.zip",
    )


# 详细信息：基础信息/EXIF/标签/派生关系
@bp.get("/api/images/<int:image_id>")
@jwt_required()
def image_detail(image_id: int):
    g.user_id = _current_user_id_from_jwt()
    visibility_sql = ", i.visibility" if _has_visibility_column() else ""
    row = query(
        f"""
        SELECT i.id, i.title, i.description, i.stored_path, i.path, i.parent_id,
               i.mime_type, COALESCE(i.size_bytes, i.size) AS size_bytes,
               i.width, i.height, i.created_at, i.updated_at, i.taken_at
               {visibility_sql},
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
        "visibility": img.get("visibility") if _has_visibility_column() else None,
        "url": url,
        "width": img.get("width"),
        "height": img.get("height"),
        "sizeMB": round((img.get("size_bytes") or 0) / 1024 / 1024, 1) if img.get("size_bytes") is not None else None,
        "format": (img.get("mime_type") or "").split("/")[-1].upper() if img.get("mime_type") else None,
        "createdAt": img.get("created_at").strftime("%Y-%m-%d %H:%M:%S") if img.get("created_at") else None,
        "updatedAt": img.get("updated_at").strftime("%Y-%m-%d %H:%M:%S") if img.get("updated_at") else None,
        "takenAt": img.get("taken_at").strftime("%Y-%m-%d %H:%M:%S") if img.get("taken_at") else None,
        "tags": tags,
        "exif": exif,
        "relations": relations,
    }
    return jsonify(resp)


@bp.put("/api/images/<int:image_id>")
@jwt_required()
def update_image_meta(image_id: int):
    g.user_id = _current_user_id_from_jwt()
    data = request.get_json(silent=True) or {}

    fields = []
    params = []
    if "title" in data:
        fields.append("title=%s")
        params.append((data.get("title") or "").strip() or None)
    if "description" in data:
        fields.append("description=%s")
        params.append((data.get("description") or "").strip() or None)
    if "visibility" in data and _has_visibility_column():
        fields.append("visibility=%s")
        params.append((data.get("visibility") or "").strip() or None)

    if not fields:
        return jsonify({"error": "缺少可更新字段"}), 400

    fields.append("updated_at=NOW()")
    params.extend([image_id, g.user_id or 0])
    execute(
        f"UPDATE images SET {', '.join(fields)} WHERE id=%s AND owner_id=%s",
        params,
    )

    visibility_sql = ", visibility" if _has_visibility_column() else ""
    rows = query(
        f"""
        SELECT title, description, updated_at{visibility_sql}
        FROM images
        WHERE id=%s AND owner_id=%s
        LIMIT 1
        """,
        (image_id, g.user_id or 0),
    )
    if not rows:
        return jsonify({"error": "图片不存在或无权限查看"}), 404
    row = rows[0]
    resp = {
        "title": row.get("title"),
        "description": row.get("description"),
        "updatedAt": row.get("updated_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("updated_at") else None,
    }
    if _has_visibility_column():
        resp["visibility"] = row.get("visibility")
    return jsonify({"ok": True, "image": resp})


def _dedup_tags(tags, limit: int = 5):
    seen = set()
    result = []
    for t in tags or []:
        name = str(t).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
        if len(result) >= limit:
            break
    return result


@bp.post("/api/images/<int:image_id>/ai_tags")
@jwt_required()
def image_ai_tags(image_id: int):
    g.user_id = _current_user_id_from_jwt()
    row = query(
        "SELECT id, stored_path, path, title, width, height FROM images WHERE id=%s AND owner_id=%s LIMIT 1",
        (image_id, g.user_id or 0),
    )
    if not row:
        return jsonify({"error": "图片不存在或无权限查看"}), 404
    img_row = row[0]
    rel_path = (img_row.get("stored_path") or img_row.get("path") or "").strip()
    if not rel_path:
        return jsonify({"error": "图片路径缺失"}), 400

    abs_root = os.path.abspath(current_app.config["UPLOAD_DIR"])
    abs_path = os.path.join(abs_root, rel_path)
    if not os.path.exists(abs_path):
        return jsonify({"error": "图片文件不存在"}), 404

    tags = []
    try:
        result = analyze_image(abs_path)
        tags = result.get("tags") or []
    except Exception:
        tags = []

    if not tags:
        fallback = []
        base_name = os.path.splitext(os.path.basename(rel_path))[0]
        if base_name:
            fallback.extend([t for t in base_name.replace("_", " ").replace("-", " ").split() if t])
        width = img_row.get("width")
        height = img_row.get("height")
        if width and height:
            fallback.append(f"{width}x{height}")
            fallback.append("横图" if width >= height else "竖图")
        try:
            meta = extract_exif(abs_path)
            fallback.extend(meta.get("auto_tags") or [])
        except Exception:
            pass
        tags = _dedup_tags(fallback)
    else:
        tags = _dedup_tags(tags)

    return jsonify({"tags": tags})


# 简易图像处理：裁剪、旋转、亮度/对比度/饱和度/色温/锐化/缩放
def _apply_edits(img: Image.Image, params: dict) -> Image.Image:
    def _to_float(val):
        try:
            return float(val)
        except Exception:
            return None

    def _to_int(val):
        try:
            return int(val)
        except Exception:
            return None

    def _to_bool(val) -> bool:
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return bool(val)
        if isinstance(val, str):
            return val.strip().lower() in ("1", "true", "yes", "y", "on")
        return False

    # 缩放使用 LANCZOS 重采样，保证像素级缩放质量
    resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS

    # 1) 旋转（像素级旋转，使用工作台底色避免黑边）
    deg_f = _to_float(params.get("rotate")) or 0
    if deg_f % 360 != 0:
        fill_rgb = (245, 247, 250)
        try:
            img = img.rotate(-deg_f, expand=True, fillcolor=fill_rgb)
        except TypeError:
            rotated = img.convert("RGBA").rotate(-deg_f, expand=True)
            background = Image.new("RGBA", rotated.size, fill_rgb + (255,))
            background.paste(rotated, (0, 0), rotated)
            img = background.convert("RGB")

    # 2) 裁剪（基于旋转后的像素）
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

    warm_v = _to_float(params.get("warmth")) or 0
    if warm_v != 0 and img.mode == "RGB":
        warm_v = max(-100.0, min(100.0, warm_v))
        strength = abs(warm_v) / 100.0
        boost = 1 + strength * 0.6
        reduce = 1 - strength * 0.3
        r_gain = boost if warm_v > 0 else reduce
        b_gain = boost if warm_v < 0 else reduce
        r, g_, b_ = img.split()
        r = r.point(lambda v: max(0, min(255, int(v * r_gain))))
        b_ = b_.point(lambda v: max(0, min(255, int(v * b_gain))))
        img = Image.merge("RGB", (r, g_, b_))

    sharp_v = _to_float(params.get("sharpen")) or 0
    if sharp_v > 0:
        sharp_v = max(0.0, min(100.0, sharp_v))
        scale = sharp_v / 100.0
        radius = 1.2 + scale * 1.3
        percent = int(100 + scale * 300)
        img = img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=3))

    # 4) 缩放：等比缩放 + 必要时 padding，避免裁切内容
    tw = _to_int(params.get("target_width"))
    th = _to_int(params.get("target_height"))
    keep_ratio = _to_bool(params.get("keep_ratio"))
    resize_mode = (params.get("resize_mode") or "").strip().lower()
    ratio_w = _to_float(params.get("ratio_width"))
    ratio_h = _to_float(params.get("ratio_height"))
    if tw is not None and tw <= 0:
        tw = None
    if th is not None and th <= 0:
        th = None

    if tw or th:
        orig_w, orig_h = img.size
        if keep_ratio:
            if ratio_w and ratio_h and ratio_h != 0:
                if tw and not th:
                    th = int(round(tw * (ratio_h / ratio_w)))
                elif th and not tw:
                    tw = int(round(th * (ratio_w / ratio_h)))
                elif tw and th:
                    th = int(round(tw * (ratio_h / ratio_w)))
                else:
                    tw = orig_w
                    th = int(round(orig_w * (ratio_h / ratio_w)))
            else:
                if tw and not th:
                    th = int(round(tw * (orig_h / orig_w)))
                elif th and not tw:
                    tw = int(round(th * (orig_w / orig_h)))
        else:
            if tw and not th:
                th = orig_h
            elif th and not tw:
                tw = orig_w

        tw = max(1, int(tw)) if tw else None
        th = max(1, int(th)) if th else None
        if tw and th:
            try:
                if not resize_mode:
                    resize_mode = "pad" if keep_ratio else "stretch"
                if resize_mode in ("fit", "contain"):
                    resize_mode = "pad" if keep_ratio else "stretch"
                if resize_mode not in ("stretch", "pad"):
                    resize_mode = "pad" if keep_ratio else "stretch"
                if resize_mode == "pad":
                    img = ImageOps.pad(img, (tw, th), method=resample, color="white")
                else:
                    img = img.resize((tw, th), resample=resample)
            except Exception:
                pass  # 缩放异常时保持原图

    return img


# 预览渲染接口：前端 POST /api/images/<id>/preview
@bp.post("/api/images/<int:image_id>/preview")
@jwt_required()
def preview_image(image_id: int):
    g.user_id = _current_user_id_from_jwt()
    data = request.get_json(silent=True) or {}

    base_rows = query(
        "SELECT id,owner_id,stored_path,path FROM images WHERE id=%s AND owner_id=%s LIMIT 1",
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
            edited.save(buf, format="JPEG", quality=90)
            buf.seek(0)
    except Exception as e:
        return jsonify({"error": f"预览生成失败: {e}"}), 500

    resp = send_file(buf, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "no-store"
    return resp


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

    resp = {"ok": True, "image_id": target_id, "url": f"/files/{rel_out}", "mode": mode}
    stamp_row = query(
        "SELECT updated_at, created_at FROM images WHERE id=%s AND owner_id=%s LIMIT 1",
        (target_id, g.user_id or 0),
    )
    if stamp_row:
        stamp = stamp_row[0].get("updated_at") or stamp_row[0].get("created_at")
        if stamp:
            resp["updatedAt"] = stamp.strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(resp)


# ===== 标签列表（前端可用于筛选 & 上传时选择）=====
@bp.get("/api/tags")
@jwt_required()
def list_tags():
    g.user_id = _current_user_id_from_jwt()
    keyword = (request.args.get("q") or "").strip()
    if keyword:
        like = f"%{keyword}%"
        rows = query(
            "SELECT name FROM tags WHERE owner_id=%s AND name LIKE %s ORDER BY name LIMIT 50",
            (g.user_id, like),
        )
    else:
        rows = query("SELECT name FROM tags WHERE owner_id=%s ORDER BY name", (g.user_id,))
    return jsonify([r["name"] for r in rows])
