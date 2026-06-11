"""Image preprocessing helpers for plan detector inputs."""

from __future__ import annotations

import io


def preprocess_image(content: bytes, target_size=(1024, 1024)) -> dict:
    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    except ImportError as exc:
        raise RuntimeError("Pillow is required for ML image preprocessing") from exc

    image = Image.open(io.BytesIO(content)).convert("RGB")
    original_size = image.size
    enhanced = ImageEnhance.Contrast(image).enhance(1.25)
    enhanced = enhanced.filter(ImageFilter.SHARPEN)
    resized = enhanced.resize(target_size)
    linework = ImageOps.grayscale(resized).point(
        lambda value: 255 if value > 190 else 0)
    return {
        "image": resized,
        "thresholded_linework": linework,
        "original_width": original_size[0],
        "original_height": original_size[1],
        "input_width": target_size[0],
        "input_height": target_size[1],
    }
