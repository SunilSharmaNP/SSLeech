#!/usr/bin/env python3
from traceback import format_exc
from asyncio import sleep
from aiofiles.os import remove as aioremove
from random import choice as rchoice
from time import time
from re import match as re_match
from cryptography.fernet import InvalidToken

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import InputMediaPhoto

from pyrogram.errors import (
    ReplyMarkupInvalid,
    FloodWait,
    PeerIdInvalid,
    ChannelInvalid,
    RPCError,
    UserNotParticipant,
    MessageNotModified,
    MessageEmpty,
    PhotoInvalidDimensions,
    WebpageCurlFailed,
    MediaEmpty,
    DocumentInvalid,
)

from bot import (
    config_dict,
    user_data,
    categories_dict,
    bot_cache,
    LOGGER,
    bot_name,
    status_reply_dict,
    status_reply_dict_lock,
    Interval,
    bot,
    user,
    download_dict_lock,
)
from bot.helper.ext_utils.bot_utils import (
    get_readable_message,
    setInterval,
    sync_to_async,
    download_image_url,
    fetch_user_tds,
    fetch_user_dumps,
    new_thread,
)
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.ext_utils.exceptions import TgLinkException
from bot.helper.themes.custom_emojis import CUSTOM_EMOJI_MAP

import re as _re

# Sorted longest-first so multi-char sequences match before their base chars.
# Built once at import time and used by _inject_html_emoji().
_SORTED_EMOJI_MAP: list = []

# Matches existing <emoji ...>...</emoji> blocks so we skip them.
_EMOJI_TAG_RE = _re.compile(r'(<emoji\b[^>]*>.*?</emoji>)', _re.DOTALL)

# Strips injected <emoji id=DOC_ID>CHAR</emoji> tags → keeps only the visible char.
_STRIP_EMOJI_RE = _re.compile(r'<emoji\b[^>]*>(.*?)</emoji>', _re.DOTALL)


def _strip_emoji_tags(text: str) -> str:
    """Remove <emoji id=...>char</emoji> wrappers, keeping only the visible char."""
    return _STRIP_EMOJI_RE.sub(r'\1', text) if text else text


def _rebuild_sorted_map():
    global _SORTED_EMOJI_MAP
    _SORTED_EMOJI_MAP = sorted(
        CUSTOM_EMOJI_MAP.items(),
        key=lambda kv: len(kv[0]),
        reverse=True,
    )


_rebuild_sorted_map()


def _inject_html_emoji(text: str) -> str:
    """Replace plain emoji chars in *text* with <emoji id=DOC_ID>char</emoji>.

    pyrotgfork 2.2.23 parses these tags natively in HTML parse mode and
    renders them as animated premium emoji.

    Smart double-processing protection: if the text already contains
    <emoji> tags (e.g. from wzml_minimal.py templates), only the plain-text
    segments between those tags are processed — existing tags are left intact.
    """
    if not CUSTOM_EMOJI_MAP or not text:
        return text

    def _replace_in_plain(segment: str) -> str:
        for emoji_char, doc_id in _SORTED_EMOJI_MAP:
            if emoji_char in segment:
                segment = segment.replace(
                    emoji_char,
                    f'<emoji id={doc_id}>{emoji_char}</emoji>',
                )
        return segment

    if '<emoji' not in text:
        # Fast path — no existing tags, replace directly.
        return _replace_in_plain(text)

    # Split on existing <emoji>...</emoji> blocks; alternate: plain, tag, plain, tag …
    parts = _EMOJI_TAG_RE.split(text)
    result = []
    for part in parts:
        if part.startswith('<emoji') and part.endswith('</emoji>'):
            result.append(part)          # already a tag — leave untouched
        else:
            result.append(_replace_in_plain(part))
    return ''.join(result)


def _preview_text(text: str, max_len: int = 300) -> str:
    """Return a single-line, truncated preview for logging."""
    if not text:
        return ""
    p = text.replace("\n", " ")
    return (p[:max_len] + "...") if len(p) > max_len else p


def _get_markup_texts(reply_markup) -> str:
    """Extract button texts from reply_markup for logging (best-effort).

    Returns a comma-separated string of button texts (raw, with emoji tags).
    """
    if not reply_markup:
        return ""
    texts = []
    try:
        if hasattr(reply_markup, 'inline_keyboard'):
            kb = reply_markup.inline_keyboard
            for row in kb:
                for btn in row:
                    try:
                        if hasattr(btn, 'text') and btn.text:
                            texts.append(btn.text)
                    except Exception:
                        continue
            return ", ".join(texts)

        if isinstance(reply_markup, dict) and 'inline_keyboard' in reply_markup:
            for row in reply_markup['inline_keyboard']:
                for btn in row:
                    if isinstance(btn, dict) and 'text' in btn and btn['text']:
                        texts.append(btn['text'])
            return ", ".join(texts)

        if isinstance(reply_markup, list):
            for row in reply_markup:
                for btn in row:
                    if hasattr(btn, 'text') and btn.text:
                        texts.append(btn.text)
                    elif isinstance(btn, dict) and 'text' in btn and btn['text']:
                        texts.append(btn['text'])
            return ", ".join(texts)

    except Exception:
        LOGGER.error('Failed to extract button texts for logging', exc_info=True)
    return ", ".join(texts)


def _strip_markup_emoji_tags(reply_markup):
    """Strip custom-emoji tags from button texts inside reply_markup.

    This function is best-effort: it supports InlineKeyboardMarkup objects,
    dicts with 'inline_keyboard' and plain list-based keybords. If it can't
    modify the structure, it returns the original reply_markup.
    """
    if not reply_markup:
        return reply_markup

    try:
        # pyrogram.types.InlineKeyboardMarkup has attribute inline_keyboard
        if hasattr(reply_markup, 'inline_keyboard'):
            kb = reply_markup.inline_keyboard
            for row in kb:
                for btn in row:
                    try:
                        if hasattr(btn, 'text') and btn.text:
                            btn.text = _strip_emoji_tags(btn.text)
                    except Exception:
                        # best-effort; ignore failures for individual buttons
                        continue
            return reply_markup

        # If reply_markup is a dict (or JSON-like) produced manually
        if isinstance(reply_markup, dict) and 'inline_keyboard' in reply_markup:
            for r_idx, row in enumerate(reply_markup['inline_keyboard']):
                for b_idx, btn in enumerate(row):
                    if isinstance(btn, dict) and 'text' in btn and btn['text']:
                        reply_markup['inline_keyboard'][r_idx][b_idx]['text'] = _strip_emoji_tags(btn['text'])
            return reply_markup

        # If it's a list of lists
        if isinstance(reply_markup, list):
            for r_idx, row in enumerate(reply_markup):
                for b_idx, btn in enumerate(row):
                    # button could be InlineKeyboardButton or dict
                    if hasattr(btn, 'text') and btn.text:
                        btn.text = _strip_emoji_tags(btn.text)
                    elif isinstance(btn, dict) and 'text' in btn and btn['text']:
                        reply_markup[r_idx][b_idx]['text'] = _strip_emoji_tags(btn['text'])
            return reply_markup

    except Exception:
        # If anything goes wrong, return original markup — we don't want to
        # crash flows because of markup sanitization.
        LOGGER.error('Failed to strip emoji tags from reply_markup', exc_info=True)
        return reply_markup

    return reply_markup


async def sendMessage(message, text, buttons=None, photo=None, **kwargs):
    try:
        text = _inject_html_emoji(text)
        if photo:
            try:
                if photo == "IMAGES":
                    photo = rchoice(config_dict["IMAGES"])
                return await message.reply_photo(
                    photo=photo,
                    reply_to_message_id=message.id,
                    caption=text,
                    reply_markup=buttons,
                    disable_notification=True,
                    **kwargs,
                )
            except IndexError:
                pass
            except DocumentInvalid as di:
                # Photo is invalid — keep emoji tags and retry as text-only message
                try:
                    chat_id = getattr(message, 'chat', None) and getattr(message.chat, 'id', None)
                except Exception:
                    chat_id = None
                LOGGER.warning("sendMessage: DOCUMENT_INVALID on photo send, falling back to text-only")
                LOGGER.info(f"DOCUMENT_INVALID details(sendMessage-photo): chat={chat_id} msg_id={getattr(message, 'id', None)} preview={_preview_text(text)} buttons={_get_markup_texts(buttons)} error={di}")
                try:
                    return await message.reply(
                        text=text,
                        parse_mode=ParseMode.HTML,
                        quote=True,
                        disable_web_page_preview=True,
                        disable_notification=True,
                        reply_markup=buttons,
                    )
                except DocumentInvalid as di2:
                    # Emoji IDs also invalid — strip and send plain
                    LOGGER.info(f"sendMessage: second DOCUMENT_INVALID (text) chat={chat_id} msg_id={getattr(message, 'id', None)} error={di2}")
                    plain_text = _strip_emoji_tags(text)
                    clean_buttons = _strip_markup_emoji_tags(buttons)
                    LOGGER.info(f"Retrying without emoji: preview={_preview_text(plain_text)} buttons={_get_markup_texts(clean_buttons)}")
                    return await message.reply(
                        text=plain_text,
                        parse_mode=ParseMode.HTML,
                        quote=True,
                        disable_web_page_preview=True,
                        disable_notification=True,
                        reply_markup=clean_buttons,
                    )
            except (PhotoInvalidDimensions, WebpageCurlFailed, MediaEmpty):
                des_dir = await download_image_url(photo)
                await sendMessage(message, text, buttons, des_dir)
                await aioremove(des_dir)
                return
            except ReplyMarkupInvalid:
                raise  # let outer except ReplyMarkupInvalid retry without buttons
            except Exception as e:
                LOGGER.error(format_exc())
        parse_mode = kwargs.pop("parse_mode", ParseMode.HTML)
        return await message.reply(
            text=text,
            parse_mode=parse_mode,
            quote=True,
            disable_web_page_preview=True,
            disable_notification=True,
            reply_markup=buttons,
            reply_to_message_id=(
                rply.id
                if (rply := message.reply_to_message)
                and not rply.text
                and not rply.caption
                else None
            ),
            **kwargs,
        )
    except FloodWait as f:
        LOGGER.warning(str(f))
        await sleep(f.value * 1.2)
        return await sendMessage(message, text, buttons, photo)
    except ReplyMarkupInvalid:
        return await sendMessage(message, text, None, photo)
    except MessageEmpty:
        return await sendMessage(message, text, parse_mode=ParseMode.DISABLED)
    except DocumentInvalid as di:
        # Custom emoji IDs in text are invalid/expired — strip tags and retry plain
        try:
            chat_id = getattr(message, 'chat', None) and getattr(message.chat, 'id', None)
        except Exception:
            chat_id = None
        LOGGER.warning("sendMessage: DOCUMENT_INVALID on text send, retrying without custom emoji")
        LOGGER.info(f"DOCUMENT_INVALID details(sendMessage-text): chat={chat_id} msg_id={getattr(message, 'id', None)} preview={_preview_text(text)} buttons={_get_markup_texts(buttons)} error={di}")
        plain_text = _strip_emoji_tags(text)
        clean_buttons = _strip_markup_emoji_tags(buttons)
        try:
            return await message.reply(
                text=plain_text,
                quote=True,
                disable_web_page_preview=True,
                disable_notification=True,
                reply_markup=clean_buttons,
            )
        except Exception as e2:
            LOGGER.error(f"sendMessage: plain retry also failed: {e2}")
            return str(e2)
    except Exception as e:
        LOGGER.error(format_exc())
        return str(e)


async def sendCustomMsg(chat_id, text, buttons=None, photo=None, debug=False):
    try:
        text = _inject_html_emoji(text)
        if photo:
            try:
                if photo == "IMAGES":
                    photo = rchoice(config_dict["IMAGES"])
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    reply_markup=buttons,
                    disable_notification=True,
                )
            except IndexError:
                pass
            except DocumentInvalid as di:
                LOGGER.warning("sendCustomMsg: DOCUMENT_INVALID on photo, falling back to text-only")
                LOGGER.info(f"DOCUMENT_INVALID details(sendCustomMsg-photo): chat={chat_id} preview={_preview_text(text)} buttons={_get_markup_texts(buttons)} error={di}")
                try:
                    return await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                        disable_notification=True,
                        reply_markup=buttons,
                    )
                except DocumentInvalid as di2:
                    LOGGER.info(f"sendCustomMsg: second DOCUMENT_INVALID (text) chat={chat_id} error={di2}")
                    plain_text = _strip_emoji_tags(text)
                    clean_buttons = _strip_markup_emoji_tags(buttons)
                    LOGGER.info(f"Retrying without emoji: preview={_preview_text(plain_text)} buttons={_get_markup_texts(clean_buttons)}")
                    return await bot.send_message(
                        chat_id=chat_id,
                        text=plain_text,
                        disable_web_page_preview=True,
                        disable_notification=True,
                        reply_markup=clean_buttons,
                    )
            except (PhotoInvalidDimensions, WebpageCurlFailed, MediaEmpty):
                des_dir = await download_image_url(photo)
                await sendCustomMsg(chat_id, text, buttons, des_dir)
                await aioremove(des_dir)
                return
            except Exception as e:
                LOGGER.error(format_exc())
        return await bot.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=True,
            disable_notification=True,
            reply_markup=buttons,
        )
    except FloodWait as f:
        LOGGER.warning(str(f))
        await sleep(f.value * 1.2)
        return await sendCustomMsg(chat_id, text, buttons, photo)
    except ReplyMarkupInvalid:
        return await sendCustomMsg(chat_id, text, None, photo)
    except DocumentInvalid as di:
        LOGGER.warning("sendCustomMsg: DOCUMENT_INVALID on text send, retrying without emoji")
        LOGGER.info(f"DOCUMENT_INVALID details(sendCustomMsg-text): chat={chat_id} preview={_preview_text(text)} buttons={_get_markup_texts(buttons)} error={di}")
        plain_text = _strip_emoji_tags(text)
        clean_buttons = _strip_markup_emoji_tags(buttons)
        LOGGER.info(f"Retrying without emoji: preview={_preview_text(plain_text)} buttons={_get_markup_texts(clean_buttons)}")
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=plain_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                disable_notification=True,
                reply_markup=clean_buttons,
            )
        except Exception as e2:
            LOGGER.error(f"sendCustomMsg: plain retry failed: {e2}")
            return str(e2)
    except Exception as e:
        LOGGER.error(format_exc())
        return str(e)


async def chat_info(channel_id):
    channel_id = str(channel_id).strip()
    if channel_id.startswith("-100"):
        channel_id = int(channel_id)
    elif channel_id.startswith("@"):
        channel_id = channel_id.replace("@", "")
    else:
        return None
    try:
        return await bot.get_chat(channel_id)
    except (PeerIdInvalid, ChannelInvalid) as e:
        LOGGER.error(f"{e.NAME}: {e.MESSAGE} for {channel_id}")
        return None


async def sendMultiMessage(chat_ids, text, buttons=None, photo=None):
    text = _inject_html_emoji(text)
    msg_dict = {}
    for channel_id in chat_ids.split():
        channel_id, *topic_id = channel_id.split(":")
        topic_id = int(topic_id[0]) if len(topic_id) else None
        chat = await chat_info(channel_id)
        if chat is None:
            LOGGER.warning(f"sendMultiMessage: skipping invalid/inaccessible channel {channel_id}")
            continue
        try:
            if photo:
                try:
                    if photo == "IMAGES":
                        photo = rchoice(config_dict["IMAGES"])
                    sent = await bot.send_photo(
                        chat_id=chat.id,
                        photo=photo,
                        caption=text,
                        reply_markup=buttons,
                        reply_to_message_id=topic_id,
                        disable_notification=True,
                    )
                    msg_dict[f"{chat.id}:{topic_id}"] = sent
                except IndexError:
                    pass
                except DocumentInvalid as di:
                    LOGGER.warning(f"sendMultiMessage: DOCUMENT_INVALID on photo for {channel_id}, falling back to text-only")
                    LOGGER.info(f"DOCUMENT_INVALID details(sendMultiMessage-photo): chat={chat.id} preview={_preview_text(text)} buttons={_get_markup_texts(buttons)} error={di}")
                    try:
                        sent = await bot.send_message(
                            chat_id=chat.id,
                            text=text,
                            parse_mode=ParseMode.HTML,
                            disable_web_page_preview=True,
                            disable_notification=True,
                            reply_to_message_id=topic_id,
                            reply_markup=buttons,
                        )
                        msg_dict[f"{chat.id}:{topic_id}"] = sent
                    except DocumentInvalid as di2:
                        LOGGER.info(f"sendMultiMessage: second DOCUMENT_INVALID (text) chat={chat.id} error={di2}")
                        plain_text = _strip_emoji_tags(text)
                        clean_buttons = _strip_markup_emoji_tags(buttons)
                        LOGGER.info(f"Retrying without emoji: preview={_preview_text(plain_text)} buttons={_get_markup_texts(clean_buttons)}")
                        try:
                            sent = await bot.send_message(
                                chat_id=chat.id,
                                text=plain_text,
                                parse_mode=ParseMode.HTML,
                                disable_web_page_preview=True,
                                disable_notification=True,
                                reply_to_message_id=topic_id,
                                reply_markup=clean_buttons,
                            )
                            msg_dict[f"{chat.id}:{topic_id}"] = sent
                        except Exception as e2:
                            LOGGER.error(f"sendMultiMessage: plain fallback failed: {e2}")
                    except Exception as e2:
                        LOGGER.error(f"sendMultiMessage: plain fallback failed: {e2}")
                    continue
                except (PhotoInvalidDimensions, WebpageCurlFailed, MediaEmpty):
                    des_dir = await download_image_url(photo)
                    await sendMultiMessage(chat_ids, text, buttons, des_dir)
                    await aioremove(des_dir)
                    break
                except Exception as e:
                    LOGGER.error(str(e))
                continue
            sent = await bot.send_message(
                chat_id=chat.id,
                text=text,
                disable_web_page_preview=True,
                disable_notification=True,
                reply_to_message_id=topic_id,
                reply_markup=buttons,
            )
            msg_dict[f"{chat.id}:{topic_id}"] = sent
        except FloodWait as f:
            LOGGER.warning(str(f))
            await sleep(f.value * 1.2)
            return await sendMultiMessage(chat_ids, text, buttons, photo)
        except DocumentInvalid as di:
            LOGGER.warning(f"sendMultiMessage: DOCUMENT_INVALID on text for {channel_id}, retrying without emoji")
            LOGGER.info(f"DOCUMENT_INVALID details(sendMultiMessage-text): chat={chat.id} preview={_preview_text(text)} buttons={_get_markup_texts(buttons)} error={di}")
            plain_text = _strip_emoji_tags(text)
            clean_buttons = _strip_markup_emoji_tags(buttons)
            LOGGER.info(f"Retrying without emoji: preview={_preview_text(plain_text)} buttons={_get_markup_texts(clean_buttons)}")
            try:
                sent = await bot.send_message(
                    chat_id=chat.id,
                    text=plain_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    disable_notification=True,
                    reply_to_message_id=topic_id,
                    reply_markup=clean_buttons,
                )
                msg_dict[f"{chat.id}:{topic_id}"] = sent
            except Exception as e2:
                LOGGER.error(f"sendMultiMessage: plain retry failed: {e2}")
        except Exception as e:
            LOGGER.error(str(e))
    return msg_dict


async def editMessage(message, text, buttons=None, photo=None):
    try:
        # For edits, avoid injecting custom-emoji tags because Telegram rejects
        # premium/custom emoji in edit requests. Use visible-only text instead.
        text = _strip_emoji_tags(text)
        if message.media:
            if photo:
                photo = rchoice(config_dict["IMAGES"]) if photo == "IMAGES" else photo
                return await message.edit_media(
                    InputMediaPhoto(photo, text), reply_markup=buttons
                )
            return await message.edit_caption(
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=buttons,
            )
        await message.edit(
            text=text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=buttons,
        )
    except FloodWait as f:
        LOGGER.warning(str(f))
        await sleep(f.value * 1.2)
        return await editMessage(message, text, buttons, photo)
    except (MessageNotModified, MessageEmpty):
        pass
    except ReplyMarkupInvalid:
        return await editMessage(message, text, None, photo)
    except DocumentInvalid as di:
        # Emoji IDs invalid/expired — strip tags and retry plain
        try:
            chat_id = getattr(message, 'chat', None) and getattr(message.chat, 'id', None)
        except Exception:
            chat_id = None
        LOGGER.warning("editMessage: DOCUMENT_INVALID, retrying without custom emoji")
        LOGGER.info(f"DOCUMENT_INVALID details(editMessage): chat={chat_id} msg_id={getattr(message, 'id', None)} media={hasattr(message, 'media')} preview={_preview_text(text)} buttons={_get_markup_texts(buttons)} error={di}")
        plain_text = _strip_emoji_tags(text)
        clean_buttons = _strip_markup_emoji_tags(buttons)
        LOGGER.info(f"Retrying without emoji: preview={_preview_text(plain_text)} buttons={_get_markup_texts(clean_buttons)}")
        try:
            if message.media:
                return await message.edit_caption(
                    caption=plain_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=clean_buttons,
                )
            await message.edit(
                text=plain_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=clean_buttons,
            )
        except Exception as e2:
            LOGGER.error(f"editMessage: plain retry failed: {e2}")
            return str(e2)
    except Exception as e:
        LOGGER.error(str(e))
        return str(e)


async def editReplyMarkup(message, reply_markup):
    try:
        return await message.edit_reply_markup(reply_markup=reply_markup)
    except MessageNotModified:
        pass
    except Exception as e:
        LOGGER.error(str(e))
        return str(e)


async def sendFile(message, file, caption=None, buttons=None):
    try:
        return await message.reply_document(
            document=file,
            quote=True,
            caption=caption,
            disable_notification=True,
            reply_markup=buttons,
        )
    except FloodWait as f:
        LOGGER.warning(str(f))
        await sleep(f.value * 1.2)
        return await sendFile(message, file, caption)
    except Exception as e:
        LOGGER.error(str(e))
        return str(e)


async def deleteMessage(message):
    try:
        await message.delete()
    except Exception as e:
        LOGGER.error(str(e))


async def auto_delete_message(cmd_message=None, bot_message=None):
    if config_dict["AUTO_DELETE_MESSAGE_DURATION"] != -1:
        await sleep(config_dict["AUTO_DELETE_MESSAGE_DURATION"])
        if cmd_message is not None:
            await deleteMessage(cmd_message)
        if bot_message is not None:
            await deleteMessage(bot_message)


async def delete_links(message):
    if config_dict["DELETE_LINKS"]:
        if reply_to := message.reply_to_message:
            await deleteMessage(reply_to)
        await deleteMessage(message)


async def delete_all_messages():
    async with status_reply_dict_lock:
        for key, data in list(status_reply_dict.items()):
            try:
                del status_reply_dict[key]
                await deleteMessage(data[0])
            except Exception as e:
                LOGGER.error(str(e))


async def get_tg_link_content(link, user_id, decrypter=None):
    message = None
    user_sess = user_data.get(user_id, {}).get("usess", "")
    if link.startswith(
        (
            "https://t.me/",
            "https://telegram.me/",
            "https://telegram.dog/",
            "https://telegram.space/",
        )
    ):
        private = False
        msg = re_match(
            r"https:\/\/(t\.me|telegram\.me|telegram\.dog|telegram\.space)\/(?:c\/)?([^\/]+)(?:\/[^\/]+)?\/([0-9]+)",
            link,
        )
    else:
        private = True
        msg = re_match(
            r"tg:\/\/(openmessage)\?user_id=([0-9]+)&message_id=([0-9]+)", link
        )
        if not (user or user_sess):
            raise TgLinkException(
                "USER_SESSION_STRING or Private User Session required for this private link!"
            )

    chat = msg.group(2)
    msg_id = int(msg.group(3))
    if chat.isdigit():
        chat = int(chat) if private else int(f"-100{chat}")

    if not private:
        try:
            message = await bot.get_messages(chat_id=chat, message_ids=msg_id)
            if message.empty:
                private = True
        except Exception as e:
            private = True
            if not (user or user_sess):
                raise e

    if private and user:
        try:
            user_message = await user.get_messages(chat_id=chat, message_ids=msg_id)
            if not user_message.empty:
                return user_message, "user"
        except Exception as e:
            if not user_sess:
                raise TgLinkException(
                    f"Bot User Session  don't have access to this chat!. ERROR: {e}"
                ) from e
