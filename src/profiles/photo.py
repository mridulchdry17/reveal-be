"""Profile photos are checked and re-encoded here before they're stored.

Re-encoding is what makes an upload safe to keep: only real JPEG/PNG/WebP images get
through, the phone's rotation is applied, and EXIF (GPS, device) is dropped because
it's never copied to the new file.
"""

from collections.abc import Collection
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError

MAX_SIDE = 1600
VIEW_SIDE = 900  # what a match gets: enough for a phone, less worth taking
GRID = 3
_CLOSED = (234, 223, 211)  # a closed piece: flat, so nothing of it leaves the server
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


def pieces(data: bytes, open_pieces: Collection[int], mark: str) -> bytes:
    """The photo as one viewer may see it: closed pieces painted over, their mark on top.

    Pieces are a 3x3 grid, numbered row by row. The mark (from the viewer's id) is tiled
    faintly across the image, so a leaked screenshot points back to who took it.
    """
    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGB")
    image.thumbnail((VIEW_SIDE, VIEW_SIDE), Image.Resampling.LANCZOS)
    width, height = image.size
    draw = ImageDraw.Draw(image)
    for n in range(GRID * GRID):
        if n not in open_pieces:
            row, col = divmod(n, GRID)
            box = (
                col * width // GRID,
                row * height // GRID,
                (col + 1) * width // GRID,
                (row + 1) * height // GRID,
            )
            draw.rectangle(box, fill=_CLOSED)
    _watermark(image, mark)
    out = BytesIO()
    image.save(out, "JPEG", quality=82)
    return out.getvalue()


def blurred(data: bytes, tiny: int, side: int) -> bytes:
    """The photo so coarse that no detail survives: shrunk to `tiny` pixels on its longer
    side, blown up to `side`, and blurred again so the blocks don't show. Nothing finer
    than the tiny image can be recovered from it, whatever the viewer does to it.
    """
    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGB")
    scale = side / max(image.size)
    big_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    image.thumbnail((tiny, tiny), Image.Resampling.BOX)
    big = image.resize(big_size, Image.Resampling.BICUBIC)
    big = big.filter(ImageFilter.GaussianBlur(radius=side / tiny / 2))
    out = BytesIO()
    big.save(out, "JPEG", quality=80)
    return out.getvalue()


def _watermark(image: Image.Image, mark: str) -> None:
    font = ImageFont.load_default(size=max(14, image.width // 28))
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    step_x, step_y = max(120, image.width // 3), max(90, image.height // 5)
    for y in range(-step_y, image.height + step_y, step_y):
        offset = (y // step_y) % 2 * step_x // 2
        for x in range(-step_x + offset, image.width + step_x, step_x):
            draw.text((x, y), mark, font=font, fill=(255, 255, 255, 46))
    image.paste(Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB"))
