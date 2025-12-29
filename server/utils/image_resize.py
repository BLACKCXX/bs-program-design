from PIL import Image, ImageOps


def _ensure_size(val):
    try:
        num = int(val)
    except Exception:
        return None
    return max(1, num)


def resize_image_with_pad(img: Image.Image, target_w: int, target_h: int, background="white") -> Image.Image:
    """High quality contain-scale with padding to avoid cropping content."""
    tw = _ensure_size(target_w)
    th = _ensure_size(target_h)
    if not tw or not th:
        return img

    base_mode = img.mode
    work = img.convert("RGBA") if img.mode == "RGBA" else img.convert("RGB")
    resized = ImageOps.contain(work, (tw, th), method=Image.Resampling.LANCZOS)
    canvas_mode = resized.mode if resized.mode in ("RGBA", "RGB") else "RGB"
    canvas = Image.new(canvas_mode, (tw, th), color=background)
    offset = ((tw - resized.width) // 2, (th - resized.height) // 2)
    canvas.paste(resized, offset, resized if resized.mode == "RGBA" else None)
    return canvas.convert(base_mode) if base_mode in ("RGB", "RGBA") else canvas


def resize_with_pad(input_path: str, out_path: str, target_w: int, target_h: int, background="white", output_format=None) -> str:
    """
    Path-based helper: load from input_path, contain-scale with padding, save to out_path.
    """
    with Image.open(input_path) as img:
        result = resize_image_with_pad(img, target_w, target_h, background=background)
        fmt = output_format or (img.format or "JPEG")
        result.save(out_path, format=fmt)
    return out_path
