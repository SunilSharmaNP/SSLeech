#!/usr/bin/env python3
"""
Shared helper for pulling a Telegram message across multiple independent
Pyrogram sessions (the bot session, the optional premium user session, and
any ADDITIONAL_BOT_TOKENS sessions).

A Telegram `file_reference` is only valid for the session that fetched it,
so it can't be shared across sessions directly. If BIN_CHANNEL is
configured (every session added there as admin), the primary session
copies the source message into BIN_CHANNEL once; every other session then
independently resolves its OWN copy from BIN_CHANNEL (or, if BIN_CHANNEL
isn't set, from the original chat — which only works for sessions that are
already members there). Sessions that can't resolve a copy are skipped.

Used by both the internal fast-download path (telegram_download.py) and
the public /link command (tg_stream_server.py + bot/modules/link_gen.py).
"""

from logging import getLogger

LOGGER = getLogger(__name__)


def available_sessions(primary_client=None):
    """Distinct, already-connected Telegram sessions we can pull from in
    parallel. Splitting work across the SAME session doesn't help (Telegram
    throttles per-session bandwidth) — real speedup only comes from
    genuinely separate sessions."""
    from bot import bot, user, EXTRA_BOT_CLIENTS

    sessions = []
    seen = set()
    for c in (primary_client, bot, user, *EXTRA_BOT_CLIENTS):
        if c and not isinstance(c, str) and id(c) not in seen:
            sessions.append(c)
            seen.add(id(c))
    return sessions


async def copy_to_bin_channel(primary_client, message):
    from bot import BIN_CHANNEL

    if not BIN_CHANNEL:
        return None
    try:
        return await primary_client.copy_message(
            chat_id=BIN_CHANNEL,
            from_chat_id=message.chat.id,
            message_id=message.id,
        )
    except Exception as e:
        LOGGER.warning(
            f"BIN_CHANNEL copy failed ({e}); will only use sessions that "
            "already have direct access to the source chat"
        )
        return None


async def resolve_multi_sessions(message, primary_client=None):
    """Given a live Message object, returns (entries, bin_message) where
    entries is a list of (client, message) pairs — one per session that
    could independently resolve its own valid copy of the media."""
    from bot import bot as default_bot

    primary_client = primary_client or default_bot
    sessions = available_sessions(primary_client)
    bin_message = await copy_to_bin_channel(primary_client, message)
    source_chat_id = bin_message.chat.id if bin_message else message.chat.id
    source_message_id = bin_message.id if bin_message else message.id
    base_message = bin_message or message

    entries = []
    for c in sessions:
        msg_for_client = base_message if c is primary_client else None
        if msg_for_client is None:
            try:
                resolved = await c.get_messages(source_chat_id, source_message_id)
            except Exception:
                resolved = None
            if not resolved or not (
                resolved.media and getattr(resolved, resolved.media.value, None)
            ):
                continue
            msg_for_client = resolved
        entries.append((c, msg_for_client))
    return entries, bin_message


async def resolve_multi_sessions_by_id(chat_id, message_id, primary_client=None):
    """Used to restore persisted /link tokens after a bot restart: resolve
    every available session's own independent copy purely from
    chat_id/message_id, with no live Message object available yet."""
    sessions = available_sessions(primary_client)
    entries = []
    for c in sessions:
        try:
            resolved = await c.get_messages(chat_id, message_id)
        except Exception:
            resolved = None
        if not resolved or not (
            resolved.media and getattr(resolved, resolved.media.value, None)
        ):
            continue
        entries.append((c, resolved))
    return entries
