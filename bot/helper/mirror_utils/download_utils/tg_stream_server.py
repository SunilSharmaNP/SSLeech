#!/usr/bin/env python3
"""
Local-only HTTP direct-link server for Telegram media.

Concept ported/adapted from fyaz05/FileToLink (the "Thunder" project):
  - ByteStreamer.stream_file()            -> Thunder/utils/custom_dl.py
  - Range parsing + streaming response    -> Thunder/server/stream_routes.py

Instead of downloading a Telegram file to disk with Pyrogram's
download_media() (one serial MTProto stream), this module exposes the
message's media as a local HTTP URL that understands byte-range requests.
aria2c (already used by this bot for direct links/torrents) is then told to
fetch that URL, and because the URL advertises `Accept-Ranges: bytes`,
aria2c opens several parallel range requests against it — each one pulling
a different chunk straight from Telegram concurrently — which is
meaningfully faster than one single-threaded download_media() call.

The server binds to 127.0.0.1 ONLY. It is never exposed on a public port,
never needs a BIN_CHANNEL, and never needs extra bot tokens: it streams
straight from whichever client (bot or user) already has access to the
source message.
"""

import asyncio
import json
import re
import secrets
from os import path as ospath
from typing import Any, Dict, Optional
from urllib.parse import quote

from aiohttp import web
from pyrogram.errors import FloodWait

from bot import LOGGER
from bot import bot as _default_client

CHUNK_SIZE = 1024 * 1024  # Telegram CDN chunk size used by stream_media
RANGE_REGEX = re.compile(r"^bytes=(?P<start>\d*)-(?P<end>\d*)$")
PORT_FILE = "stream_port.txt"
LINKS_FILE = "link_tokens.json"

# token -> {"message": Message, "client": Client|None, "file_name", "file_size", "mime_type"}
_registry: Dict[str, Dict[str, Any]] = {}

# Public, long-lived /link tokens (survive restarts via LINKS_FILE):
# token -> {"sessions": [(client, message), ...], "chat_id", "message_id",
#           "source_chat_id", "source_message_id", "file_name", "file_size",
#           "mime_type", "rr_index"}
_link_registry: Dict[str, Dict[str, Any]] = {}

_runner: Optional[web.AppRunner] = None
_server_port: Optional[int] = None


def get_media(message):
    """Return the media object (document/video/audio/...) attached to a message, if any."""
    for attr in (
        "audio",
        "document",
        "video",
        "animation",
        "voice",
        "video_note",
        "photo",
        "sticker",
    ):
        media = getattr(message, attr, None)
        if media:
            return media
    return None


class ByteStreamer:
    """Yields raw byte chunks of a Telegram message's media directly from
    Telegram's servers, without ever touching local disk."""

    def __init__(self, client):
        self.client = client

    async def stream_file(self, message, offset: int = 0, limit: int = 0):
        chunk_offset = offset // CHUNK_SIZE
        chunk_limit = 0
        if limit > 0:
            chunk_limit = ((limit + CHUNK_SIZE - 1) // CHUNK_SIZE) + 1
        while True:
            try:
                async for chunk in self.client.stream_media(
                    message, offset=chunk_offset, limit=chunk_limit
                ):
                    yield chunk
                return
            except FloodWait as e:
                LOGGER.warning(f"tg_stream_server: FloodWait {e.value}s, retrying")
                await asyncio.sleep(e.value)


def _resolve_client(entry_client):
    return entry_client or _default_client


def register_stream(message, client=None) -> Dict[str, Any]:
    """Register a Telegram message's media for local streaming.

    Returns {"url", "file_name", "file_size"}. Raises if the server hasn't
    been started yet or the message carries no downloadable media.
    """
    if _server_port is None:
        raise RuntimeError(
            "tg_stream_server is not running yet; call start_stream_server() at bot startup"
        )

    media = get_media(message)
    if media is None:
        raise ValueError("Message has no downloadable media")

    file_size = getattr(media, "file_size", 0) or 0
    if not file_size:
        raise ValueError("Media has no known file size; cannot serve range requests")

    file_name = getattr(media, "file_name", None) or f"tg_file_{message.id}"
    mime_type = getattr(media, "mime_type", None) or "application/octet-stream"

    token = secrets.token_hex(8)
    _registry[token] = {
        "message": message,
        "client": client,
        "file_name": file_name,
        "file_size": file_size,
        "mime_type": mime_type,
    }

    url = f"http://127.0.0.1:{_server_port}/dl/{token}/{quote(file_name, safe='')}"
    return {"url": url, "file_name": file_name, "file_size": file_size}


def unregister_stream(url_or_token: str) -> None:
    token = url_or_token.rsplit("/", 2)[-2] if url_or_token.startswith("http") else url_or_token
    _registry.pop(token, None)


def _save_persisted_links() -> None:
    try:
        data = {
            token: {
                "chat_id": entry["chat_id"],
                "message_id": entry["message_id"],
                "source_chat_id": entry["source_chat_id"],
                "source_message_id": entry["source_message_id"],
                "file_name": entry["file_name"],
                "file_size": entry["file_size"],
                "mime_type": entry["mime_type"],
            }
            for token, entry in _link_registry.items()
        }
        with open(LINKS_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        LOGGER.warning(f"tg_stream_server: could not persist link tokens: {e}")


async def _load_persisted_links() -> None:
    if not ospath.exists(LINKS_FILE):
        return
    try:
        with open(LINKS_FILE) as f:
            data = json.load(f)
    except Exception as e:
        LOGGER.warning(f"tg_stream_server: could not read {LINKS_FILE}: {e}")
        return

    from bot.helper.ext_utils.multi_session import resolve_multi_sessions_by_id

    restored = 0
    for token, meta in data.items():
        try:
            entries = await resolve_multi_sessions_by_id(
                meta["chat_id"], meta["message_id"]
            )
        except Exception:
            entries = []
        if not entries:
            continue
        _link_registry[token] = {
            "sessions": entries,
            "chat_id": meta["chat_id"],
            "message_id": meta["message_id"],
            "source_chat_id": meta.get("source_chat_id", meta["chat_id"]),
            "source_message_id": meta.get("source_message_id", meta["message_id"]),
            "file_name": meta["file_name"],
            "file_size": meta["file_size"],
            "mime_type": meta["mime_type"],
            "rr_index": 0,
        }
        restored += 1
    if restored:
        LOGGER.info(f"tg_stream_server: restored {restored} persisted /link token(s)")


class BaseUrlNotSetError(RuntimeError):
    """Raised when a PUBLIC /link URL is requested but BASE_URL is not configured.

    A loopback (127.0.0.1) URL is useless to an end user — it only resolves
    inside the dyno/container itself — so we must never hand one out as a
    "working" link. Instead this forces the caller to surface an actionable
    error telling the admin to set BASE_URL.
    """


def _link_public_url(token: str, file_name: str) -> str:
    from bot import config_dict

    base = (config_dict.get("BASE_URL") or "").rstrip("/")
    if not base:
        raise BaseUrlNotSetError(
            "BASE_URL is not set, so a public /link URL cannot be generated. "
            "Set BASE_URL in /botsettings (Config Variables) to your app's public "
            "HTTPS URL, e.g. https://your-app-name.herokuapp.com — then try /link again."
        )
    path = f"/link/{token}/{quote(file_name, safe='')}"
    return f"{base}{path}"


async def register_link(message, primary_client=None) -> Dict[str, Any]:
    """Register a message for a PUBLIC, long-lived direct-download link
    (used by /link{suffix}). Unlike register_stream(), this persists across
    restarts and round-robins across every Telegram session that can
    independently resolve the file (bot / premium user / extra bot tokens),
    for real added throughput under concurrent range requests."""
    from bot.helper.ext_utils.multi_session import resolve_multi_sessions

    if _server_port is None:
        raise RuntimeError(
            "tg_stream_server is not running yet; call start_stream_server() at bot startup"
        )

    media = get_media(message)
    if media is None:
        raise ValueError("Message has no downloadable media")
    file_size = getattr(media, "file_size", 0) or 0
    if not file_size:
        raise ValueError("Media has no known file size; cannot serve range requests")
    file_name = getattr(media, "file_name", None) or f"tg_file_{message.id}"
    mime_type = getattr(media, "mime_type", None) or "application/octet-stream"

    for token, entry in _link_registry.items():
        if (
            entry.get("source_chat_id") == message.chat.id
            and entry.get("source_message_id") == message.id
        ):
            return {
                "url": _link_public_url(token, entry["file_name"]),
                "file_name": entry["file_name"],
                "file_size": entry["file_size"],
                "mime_type": entry["mime_type"],
            }

    entries, bin_message = await resolve_multi_sessions(message, primary_client)
    if not entries:
        raise RuntimeError("No Telegram session could resolve this message for streaming")

    resolved_chat_id = bin_message.chat.id if bin_message else message.chat.id
    resolved_message_id = bin_message.id if bin_message else message.id

    token = secrets.token_hex(8)
    _link_registry[token] = {
        "sessions": entries,
        "chat_id": resolved_chat_id,
        "message_id": resolved_message_id,
        "source_chat_id": message.chat.id,
        "source_message_id": message.id,
        "file_name": file_name,
        "file_size": file_size,
        "mime_type": mime_type,
        "rr_index": 0,
    }
    _save_persisted_links()

    return {
        "url": _link_public_url(token, file_name),
        "file_name": file_name,
        "file_size": file_size,
        "mime_type": mime_type,
    }


def _parse_range(range_header: str, file_size: int):
    if not range_header:
        return 0, file_size - 1
    m = RANGE_REGEX.fullmatch(range_header.strip())
    if not m:
        raise web.HTTPBadRequest(text="Invalid Range header")
    start_s, end_s = m.group("start"), m.group("end")
    if start_s:
        start = int(start_s)
        end = int(end_s) if end_s else file_size - 1
    elif end_s:
        suffix = int(end_s)
        start = max(file_size - suffix, 0)
        end = file_size - 1
    else:
        raise web.HTTPBadRequest(text="Invalid Range header")
    if start < 0 or end >= file_size or start > end:
        raise web.HTTPRequestRangeNotSatisfiable(
            headers={"Content-Range": f"bytes */{file_size}"}
        )
    return start, end


def _stream_headers(file_name, mime_type, file_size, range_header):
    start, end = _parse_range(range_header, file_size)
    content_length = end - start + 1
    headers = {
        "Content-Type": mime_type,
        "Content-Length": str(content_length),
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file_name, safe='')}",
        "Accept-Ranges": "bytes",
    }
    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    status = 206 if range_header else 200
    return start, content_length, headers, status


async def _stream_body(request, client, message, start, content_length, headers, status):
    if request.method == "HEAD":
        return web.Response(status=status, headers=headers)

    streamer = ByteStreamer(client)

    async def body_gen():
        bytes_sent = 0
        bytes_to_skip = start % CHUNK_SIZE
        async for chunk in streamer.stream_file(message, offset=start, limit=content_length):
            if bytes_to_skip:
                if len(chunk) <= bytes_to_skip:
                    bytes_to_skip -= len(chunk)
                    continue
                chunk = chunk[bytes_to_skip:]
                bytes_to_skip = 0
            remaining = content_length - bytes_sent
            if remaining <= 0:
                break
            if len(chunk) > remaining:
                chunk = chunk[:remaining]
            if chunk:
                yield chunk
                bytes_sent += len(chunk)
            if bytes_sent >= content_length:
                break

    resp = web.StreamResponse(status=status, headers=headers)
    await resp.prepare(request)
    async for chunk in body_gen():
        await resp.write(chunk)
    await resp.write_eof()
    return resp


async def _handle_download(request: web.Request):
    token = request.match_info["token"]
    entry = _registry.get(token)
    if not entry:
        raise web.HTTPNotFound(text="Unknown or expired stream token")

    range_header = request.headers.get("Range", "")
    start, content_length, headers, status = _stream_headers(
        entry["file_name"], entry["mime_type"], entry["file_size"], range_header
    )
    return await _stream_body(
        request, _resolve_client(entry["client"]), entry["message"], start, content_length, headers, status
    )


async def _handle_link_download(request: web.Request):
    token = request.match_info["token"]
    entry = _link_registry.get(token)
    if not entry:
        raise web.HTTPNotFound(text="Unknown or expired link")

    sessions = entry["sessions"]
    idx = entry["rr_index"] % len(sessions)
    entry["rr_index"] += 1
    client, message = sessions[idx]

    range_header = request.headers.get("Range", "")
    start, content_length, headers, status = _stream_headers(
        entry["file_name"], entry["mime_type"], entry["file_size"], range_header
    )
    return await _stream_body(request, client, message, start, content_length, headers, status)


async def start_stream_server(preferred_port: int = 8199) -> int:
    """Idempotently start the loopback-only stream server. Returns the bound port."""
    global _runner, _server_port
    if _runner is not None:
        return _server_port

    app = web.Application()
    app.router.add_route("GET", "/dl/{token}/{name}", _handle_download)
    app.router.add_route("HEAD", "/dl/{token}/{name}", _handle_download)
    app.router.add_route("GET", "/link/{token}/{name}", _handle_link_download)
    app.router.add_route("HEAD", "/link/{token}/{name}", _handle_link_download)

    runner = web.AppRunner(app)
    await runner.setup()

    port = preferred_port
    site = None
    for _attempt in range(20):
        try:
            site = web.TCPSite(runner, "127.0.0.1", port)
            await site.start()
            break
        except OSError:
            port += 1
            site = None
    if site is None:
        await runner.cleanup()
        raise RuntimeError("tg_stream_server: could not bind to any local port")

    _runner = runner
    _server_port = port
    try:
        with open(PORT_FILE, "w") as f:
            f.write(str(port))
    except Exception as e:
        LOGGER.warning(f"tg_stream_server: could not write {PORT_FILE}: {e}")

    LOGGER.info(
        f"tg_stream_server: local TG-to-link server listening on 127.0.0.1:{port} (loopback only)"
    )

    try:
        await _load_persisted_links()
    except Exception as e:
        LOGGER.error(f"tg_stream_server: failed to restore persisted links: {e}")

    return port
