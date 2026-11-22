"""Voice notes: what the browser recorded, checked from the bytes and kept as-is.

Browsers record WebM/Opus (Chrome, Android) or MP4/AAC (Safari, iPhone). Re-encoding
would need ffmpeg on a small VM, and a fresh in-app recording carries no location or
device data worth stripping, so we only check the container type and size.
"""

# container type -> MIME type we serve it back with
VOICE_TYPES = {"webm": "audio/webm", "mp4": "audio/mp4", "ogg": "audio/ogg"}


def detect_audio_type(data: bytes) -> str | None:
    """Container from the bytes themselves; never trust the browser's content type."""
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if data[4:8] == b"ftyp":
        return "mp4"
    if data.startswith(b"OggS"):
        return "ogg"
    return None
