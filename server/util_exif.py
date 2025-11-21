# util_exif.py — 使用 Pillow 读取图片尺寸 & EXIF（时间/设备/GPS）
from PIL import Image, ExifTags
from datetime import datetime

#advise 支持 HEIC/HEIF：有 pillow-heif 则注册，否则保持兼容（无库时仅记录不了 HEIC）
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

def _ratio_to_float(x):
    try:
        return x[0] / x[1]
    except Exception:
        return float(x)

def _gps_to_deg(gps):
    # gps: ((deg),(min),(sec))，还需配合 N/S/E/W 判断正负
    d, m, s = gps
    return _ratio_to_float(d) + _ratio_to_float(m) / 60.0 + _ratio_to_float(s) / 3600.0
"""
def extract_exif(file_path):
    
    #返回: dict(width,height,taken_at,make,model,lat,lng) 与 auto_tags(list[str])
    
    img = Image.open(file_path)
    width, height = img.size

    exif = {}
    if hasattr(img, "_getexif") and img._getexif():
        raw = img._getexif() or {}
        exif = { ExifTags.TAGS.get(k, k): v for k, v in raw.items() }

    # 时间
    dt = exif.get("DateTimeOriginal") or exif.get("DateTime")
    taken_at = None
    if isinstance(dt, str):
        # EXIF 时间格式: "YYYY:MM:DD HH:MM:SS"
        try:
            taken_at = datetime.strptime(dt, "%Y:%m:%d %H:%M:%S")
        except Exception:
            taken_at = None

    # 设备
    make  = exif.get("Make")
    model = exif.get("Model")

    # GPS
    lat = lng = None
    gps = exif.get("GPSInfo")
    if isinstance(gps, dict):
        ref_lat = gps.get(1)           # 'N' 或 'S'
        ref_lng = gps.get(3)           # 'E' 或 'W'
        gps_lat = gps.get(2)           # [(deg),(min),(sec)]
        gps_lng = gps.get(4)
        try:
            if gps_lat and gps_lng:
                lat = _gps_to_deg(gps_lat)
                lng = _gps_to_deg(gps_lng)
                if ref_lat in ("S", "s"): lat = -lat
                if ref_lng in ("W", "w"): lng = -lng
        except Exception:
            lat = lng = None

    # 自动标签（按作业要求）
    auto_tags = []
    if taken_at: auto_tags.append(f"时间:{taken_at.strftime('%Y-%m')}")
    auto_tags.append(f"分辨率:{width}x{height}")
    if model: auto_tags.append(f"设备:{model}")
    if lat is not None and lng is not None:
        auto_tags.append(f"地点:{round(lat,4)},{round(lng,4)}")

    return {
        "width": width, "height": height,
        "taken_at": taken_at, "camera_make": make, "camera_model": model,
        "gps_lat": lat, "gps_lng": lng,
        "auto_tags": auto_tags
    }
"""

def extract_exif(file_path):
    """
    从图片文件中提取常用 EXIF 信息 + 自动标签。
    返回一个 dict，尽量只包含 Python 基本类型，方便写入数据库/序列化：
    {
        "width": int | None,
        "height": int | None,
        "taken_at": datetime | None,
        "camera_make": str | None,
        "camera_model": str | None,
        "gps_lat": float | None,
        "gps_lng": float | None,
        "f_number": float | None,
        "exposure_time": str | None,
        "iso": int | None,
        "focal_length": float | None,
        "extra": dict | None,
        "auto_tags": [str, ...],
    }
    """
    width = height = None
    taken_at = None
    make = model = None
    f_number = None
    exposure_time = None
    iso = None
    focal_length = None
    lat = lng = None
    extra = {}

    # 1. 打开图片，读取基础信息（宽高 + 原始 EXIF）
    try:
        with Image.open(file_path) as img:
            width, height = img.size
            raw_exif = getattr(img, "_getexif", lambda: None)()
    except Exception:
        raw_exif = None

    # 2. 解析 EXIF
    if raw_exif:
        # 把 EXIF tag id -> 名称，方便后面按名字取值
        exif = {}
        for tag_id, value in raw_exif.items():
            tag_name = ExifTags.TAGS.get(tag_id, tag_id)
            exif[tag_name] = value

        # --- 基本信息：相机品牌/型号 ---
        make = exif.get("Make")
        model = exif.get("Model")

        # --- 拍摄时间：优先 DateTimeOriginal -> DateTimeDigitized -> DateTime ---
        dt_value = exif.get("DateTimeOriginal") or exif.get("DateTimeDigitized") or exif.get("DateTime")
        if isinstance(dt_value, bytes):
            dt_value = dt_value.decode(errors="ignore")
        if isinstance(dt_value, str):
            dt_value = dt_value.strip()
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    taken_at = datetime.strptime(dt_value, fmt)
                    break
                except Exception:
                    continue

        # --- 光圈 FNumber，通常为分数，如 (28,10) 代表 F2.8 ---
        f_val = exif.get("FNumber")
        if f_val:
            try:
                f_number = _ratio_to_float(f_val)
            except Exception:
                pass

        # --- 曝光时间 ExposureTime，常用 "1/125" 形式 ---
        exp_val = exif.get("ExposureTime")
        if exp_val:
            try:
                if isinstance(exp_val, (tuple, list)) and len(exp_val) == 2:
                    num, den = exp_val
                    exposure_time = f"{num}/{den}"
                else:
                    exposure_time = str(exp_val)
            except Exception:
                exposure_time = str(exp_val)

        # --- ISO ---
        iso_val = exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity")
        if isinstance(iso_val, (list, tuple)) and iso_val:
            iso_val = iso_val[0]
        try:
            iso = int(iso_val) if iso_val is not None else None
        except Exception:
            iso = None

        # --- 焦距 FocalLength ---
        focal_val = exif.get("FocalLength")
        if focal_val:
            try:
                focal_length = _ratio_to_float(focal_val)
            except Exception:
                pass

        # --- GPS 信息 ---
        gps_info = exif.get("GPSInfo")
        if gps_info:
            gps_data = {}
            for key, val in gps_info.items():
                name = ExifTags.GPSTAGS.get(key, key)
                gps_data[name] = val

            if "GPSLatitude" in gps_data and "GPSLatitudeRef" in gps_data:
                try:
                    lat = _gps_to_deg(gps_data["GPSLatitude"])
                    if gps_data["GPSLatitudeRef"] in ("S", b"S"):
                        lat = -lat
                except Exception:
                    lat = None

            if "GPSLongitude" in gps_data and "GPSLongitudeRef" in gps_data:
                try:
                    lng = _gps_to_deg(gps_data["GPSLongitude"])
                    if gps_data["GPSLongitudeRef"] in ("W", b"W"):
                        lng = -lng
                except Exception:
                    lng = None

            # 把原始 GPS 信息简单塞到 extra 里，便于后续调试
            try:
                extra["gps_raw"] = {k: str(v) for k, v in gps_data.items()}
            except Exception:
                pass

        # 其它未单独建字段但可能有用的信息，也可以选一部分塞进 extra
        if "Orientation" in exif:
            extra["Orientation"] = exif["Orientation"]

    if not extra:
        extra = None

    # 3. 自动标签（按作业要求）
    auto_tags = []
    if taken_at:
        auto_tags.append(f"时间:{taken_at.strftime('%Y-%m')}")
    if width and height:
        auto_tags.append(f"分辨率:{width}x{height}")
    if model:
        auto_tags.append(f"设备:{model}")
    if lat is not None and lng is not None:
        auto_tags.append(f"地点:{round(lat, 4)},{round(lng, 4)}")

    return {
        "width": width,
        "height": height,
        "taken_at": taken_at,
        "camera_make": make,
        "camera_model": model,
        "gps_lat": lat,
        "gps_lng": lng,
        "f_number": f_number,
        "exposure_time": exposure_time,
        "iso": iso,
        "focal_length": focal_length,
        "extra": extra,
        "auto_tags": auto_tags,
    }

