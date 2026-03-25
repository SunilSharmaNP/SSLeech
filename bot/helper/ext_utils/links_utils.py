"""Small helpers for detecting media in Pyrogram `Message` objects.

Provides `is_media(message)` which returns the underlying media object
(e.g., `message.document`, `message.video`, `message.photo`, etc.) or
`None` when no media is present. This mirrors the expected interface from
the original ported code.
"""

def is_media(message):
    """Return the media object contained in `message` or None.

    The returned object is the Pyrogram media object (Document, Video,
    Photo, Audio, Voice, Sticker, etc.) so callers can access attributes
    like `file_id`, `file_name`, and `mime_type`.
    """
    if message is None:
        return None
    # Prefer document (can be subtitle/image/document)
    if getattr(message, "document", None):
        return message.document
    if getattr(message, "video", None):
        return message.video
    if getattr(message, "photo", None):
        return message.photo
    if getattr(message, "audio", None):
        return message.audio
    if getattr(message, "voice", None):
        return message.voice
    if getattr(message, "sticker", None):
        return message.sticker
    return None


from urllib.parse import urlparse, unquote
import re

from bot.helper.ext_utils.bot_utils import is_url as _is_url


def is_url(url):
    return _is_url(url)


def get_link(message):
    """Extract first URL-like token from `message` or its reply.

    Returns empty string when none found.
    """
    if message is None:
        return ""
    candidates = []
    if getattr(message, "text", None):
        candidates.append(message.text)
    if getattr(message, "caption", None):
        candidates.append(message.caption)
    if getattr(message, "reply_to_message", None):
        r = message.reply_to_message
        if getattr(r, "text", None):
            candidates.append(r.text)
        if getattr(r, "caption", None):
            candidates.append(r.caption)

    for txt in candidates:
        for token in re.split(r"\s+", txt):
            token = token.strip()
            if token and is_url(token):
                return token
    return ""


def get_url_name(url):
    """Return a readable name for `url` (last path segment or hostname)."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        path = parsed.path or ""
        name = unquote(path.split("/")[-1]) if path.strip("/") else parsed.netloc
        return name or parsed.netloc
    except Exception:
        return url
