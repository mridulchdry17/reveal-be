"""Profile photos are checked and re-encoded here before they're stored.

Re-encoding is what makes an upload safe to keep: only real JPEG/PNG/WebP images get
through, the phone's rotation is applied, and EXIF (GPS, device) is dropped because
it's never copied to the new file.
"""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 1600
MAX_PIXELS = 40_000_000  # refuse huge images before decoding them (the VM has <1 GB RAM)
_FORMATS = {"JPEG", "PNG", "WEBP"}


def reencode(data: bytes) -> bytes | None:
    """A clean JPEG, at most MAX_SIDE on its longer side, or None if it isn't a photo."""
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in _FORMATS or image.width * image.height > MAX_PIXELS:
                return None
            image.draft("RGB", (MAX_SIDE * 2, MAX_SIDE * 2))  # cheap downscale for JPEGs
            upright = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        return None
    upright.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    out = BytesIO()
    upright.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()
