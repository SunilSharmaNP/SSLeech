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
import re
import secrets
from typing import Any, Dict, Optional
from urllib.parse import quote

from aiohttp import web
from pyrogram.errors import FloodWait

from bot import LOGGER
from bot import bot as _default_client

CHUNK_SIZE = 1024 * 1024  # Telegram CDN chunk size used by stream_media
RANGE_REGEX = re.compile(r"^bytes=(?P<start>\d*)-(?P<end>\d*)$")

# token -> {"message": Message, "client": Client|None, "file_name", "file_size", "mime_type"}
_registry: Dict[str, Dict[str, Any]] = {}
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


async def _handle_download(request: web.Request):
    token = request.match_info["token"]
    entry = _registry.get(token)
    if not entry:
        raise web.HTTPNotFound(text="Unknown or expired stream token")

    file_size = entry["file_size"]
    range_header = request.headers.get("Range", "")
    start, end = _parse_range(range_header, file_size)
    content_length = end - start + 1

    headers = {
        "Content-Type": entry["mime_type"],
        "Content-Length": str(content_length),
        "Content-Disposition": (
            f"attachment; filename*=UTF-8''{quote(entry['file_name'], safe='')}"
        ),
        "Accept-Ranges": "bytes",
    }
    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    status = 206 if range_header else 200

    if request.method == "HEAD":
        return web.Response(status=status, headers=headers)

    streamer = ByteStreamer(_resolve_client(entry["client"]))

    async def body_gen():
        bytes_sent = 0
        bytes_to_skip = start % CHUNK_SIZE
        async for chunk in streamer.stream_file(
            entry["message"], offset=start, limit=content_length
        ):
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


async def start_stream_server(preferred_port: int = 8199) -> int:
    """Idempotently start the loopback-only stream server. Returns the bound port."""
    global _runner, _server_port
    if _runner is not None:
        return _server_port

    app = web.Application()
    app.router.add_route("GET", "/dl/{token}/{name}", _handle_download)
    app.router.add_route("HEAD", "/dl/{token}/{name}", _handle_download)

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
    LOGGER.info(
        f"tg_stream_server: local TG-to-link server listening on 127.0.0.1:{port} (loopback only)"
    )
    return port
