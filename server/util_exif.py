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
        if x is None:
            return None
        if isinstance(x, (tuple, list)) and len(x) == 2:
            if not x[1]:
                return None
            return x[0] / x[1]
        return float(x)
    except Exception:
        return None

def _gps_to_deg(gps):
    # gps: ((deg),(min),(sec))，还需配合 N/S/E/W 判断正负
    d, m, s = gps
    d_val = _ratio_to_float(d)
    m_val = _ratio_to_float(m)
    s_val = _ratio_to_float(s)
    if d_val is None or m_val is None or s_val is None:
        return None
    return d_val + m_val / 60.0 + s_val / 3600.0

def _safe_text(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode(errors="ignore").strip()
    return str(value).strip()

def _format_lens_spec(value):
    if not isinstance(value, (tuple, list)) or len(value) < 4:
        return None
    f_min = _ratio_to_float(value[0])
    f_max = _ratio_to_float(value[1])
    a_min = _ratio_to_float(value[2])
    a_max = _ratio_to_float(value[3])
    if f_min is None or f_max is None or a_min is None or a_max is None:
        return None
    if abs(f_min - f_max) < 0.01:
        focal = f"{f_min:.0f}"
    else:
        focal = f"{f_min:.0f}-{f_max:.0f}"
    if abs(a_min - a_max) < 0.01:
        aperture = f"f/{a_min:.1f}"
    else:
        aperture = f"f/{a_min:.1f}-{a_max:.1f}"
    return f"{focal}mm {aperture}"

def _format_exposure_time(seconds):
    try:
        if seconds is None:
            return None
        sec = float(seconds)
    except Exception:
        return None
    if sec <= 0:
        return None
    if sec >= 1:
        text = f"{sec:.2f}".rstrip("0").rstrip(".")
        return f"{text}s"
    denom = round(1 / sec)
    if denom <= 0:
        return None
    return f"1/{denom}"

def _read_exif(img):
    raw = None
    try:
        raw = img.getexif()
    except Exception:
        raw = None
    if not raw:
        try:
            raw = getattr(img, "_getexif", lambda: None)()
        except Exception:
            raw = None
    exif = {}
    if not raw:
        return exif
    try:
        items = raw.items()
    except Exception:
        items = raw.items() if hasattr(raw, "items") else raw
    for tag_id, value in items:
        tag_name = ExifTags.TAGS.get(tag_id, tag_id)
        exif[tag_name] = value
    if hasattr(raw, "get_ifd") and hasattr(ExifTags, "IFD"):
        for ifd_name in ("Exif", "GPSInfo"):
            try:
                ifd_id = getattr(ExifTags.IFD, ifd_name)
                ifd = raw.get_ifd(ifd_id)
                for tag_id, value in ifd.items():
                    tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag_name not in exif:
                        exif[tag_name] = value
            except Exception:
                continue
    return exif
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
    lens_make = None
    lens_model = None
    lens_spec = None
    lens = None
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
            exif = _read_exif(img)
    except Exception:
        exif = {}

    # 2. 解析 EXIF
    if exif:
        # 把 EXIF tag id -> 名称，方便后面按名字取值

        # --- 基本信息：相机品牌/型号 ---
        make = _safe_text(exif.get("Make"))
        model = _safe_text(exif.get("Model"))
        lens_make = _safe_text(exif.get("LensMake"))
        lens_model = _safe_text(exif.get("LensModel"))
        lens_spec = exif.get("LensSpecification") or exif.get("LensInfo")
        lens_spec = _format_lens_spec(lens_spec)
        lens = " ".join([v for v in [lens_make, lens_model] if v]).strip()
        if not lens:
            lens = lens_model or lens_make or lens_spec

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
        if f_number is None:
            av_val = exif.get("ApertureValue")
            if av_val:
                try:
                    av_num = _ratio_to_float(av_val)
                    if av_num is not None:
                        f_number = 2 ** (av_num / 2)
                except Exception:
                    pass

        # --- 曝光时间 ExposureTime，常用 "1/125" 形式 ---
        exp_val = exif.get("ExposureTime")
        if exp_val:
            try:
                if isinstance(exp_val, (tuple, list)) and len(exp_val) == 2:
                    num, den = exp_val
                    exposure_time = f"{num}/{den}" if den else str(exp_val)
                else:
                    exp_num = _ratio_to_float(exp_val)
                    exposure_time = _format_exposure_time(exp_num) or str(exp_val)
            except Exception:
                exposure_time = str(exp_val)
        if not exposure_time:
            ss_val = exif.get("ShutterSpeedValue")
            ss_num = _ratio_to_float(ss_val)
            if ss_num is not None:
                exposure_time = _format_exposure_time(2 ** (-ss_num))

        # --- ISO ---
        iso_val = exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity") or exif.get("ISO")
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
        if focal_length is None:
            focal_35 = exif.get("FocalLengthIn35mmFilm")
            if focal_35:
                try:
                    focal_length = _ratio_to_float(focal_35)
                except Exception:
                    pass

        # --- GPS 信息 ---
        gps_data = {}
        gps_info = exif.get("GPSInfo") or exif.get(34853)
        if gps_info:
            if hasattr(gps_info, "items"):
                items = gps_info.items()
            elif isinstance(gps_info, (list, tuple)):
                items = gps_info
            else:
                items = []
            for key, val in items:
                name = ExifTags.GPSTAGS.get(key, key)
                gps_data[name] = val
        for key in ("GPSLatitude", "GPSLatitudeRef", "GPSLongitude", "GPSLongitudeRef", "GPSAltitude", "GPSAltitudeRef"):
            if key in exif and key not in gps_data:
                gps_data[key] = exif.get(key)

        if gps_data:
            try:
                ref_lat = _safe_text(gps_data.get("GPSLatitudeRef"))
                ref_lng = _safe_text(gps_data.get("GPSLongitudeRef"))
            except Exception:
                ref_lat = None
                ref_lng = None

            if "GPSLatitude" in gps_data:
                try:
                    lat = _gps_to_deg(gps_data["GPSLatitude"])
                    if lat is not None and ref_lat and ref_lat.upper().startswith("S"):
                        lat = -lat
                except Exception:
                    lat = None

            if "GPSLongitude" in gps_data:
                try:
                    lng = _gps_to_deg(gps_data["GPSLongitude"])
                    if lng is not None and ref_lng and ref_lng.upper().startswith("W"):
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
        "lens_make": lens_make,
        "lens_model": lens_model,
        "lens_spec": lens_spec,
        "lens": lens,
        "gps_lat": lat,
        "gps_lng": lng,
        "f_number": f_number,
        "exposure_time": exposure_time,
        "iso": iso,
        "focal_length": focal_length,
        "extra": extra,
        "auto_tags": auto_tags,
    }

