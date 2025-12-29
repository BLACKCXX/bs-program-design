def classify_device(camera_make: str, camera_model: str) -> str:
    """
    粗粒度分类拍摄设备：手机 / 平板 / 相机。
    """
    text = " ".join([camera_make or "", camera_model or ""]).lower()
    if not text.strip():
        return ""
    if any(k in text for k in ["ipad", "tablet"]):
        return "平板"
    if any(k in text for k in ["iphone", "huawei", "xiaomi", "redmi", "oppo", "vivo", "oneplus", "samsung", "pixel", "mate", "nova", "mix", "mi "]):
        return "手机"
    return "相机"
