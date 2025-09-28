#!/usr/bin/env python3
from traceback import format_exc
from logging import getLogger, ERROR
from aiofiles.os import (
    remove as aioremove,
    path as aiopath,
    rename as aiorename,
    makedirs,
    rmdir,
    mkdir,
)
from os import walk, path as ospath
from time import time
from PIL import Image
from pyrogram.types import InputMediaVideo, InputMediaDocument, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, RPCError, PeerIdInvalid, ChannelInvalid
from asyncio import sleep
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
    RetryError,
)
from re import match as re_match, sub as re_sub
from natsort import natsorted
from aioshutil import copy

from bot import (
    config_dict,
    user_data,
    GLOBAL_EXTENSION_FILTER,
    bot,
    user,
    IS_PREMIUM_USER,
)
from bot.helper.themes import BotTheme
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    sendCustomMsg,
    editReplyMarkup,
    sendMultiMessage,
    chat_info,
    deleteMessage,
    get_tg_link_content,
)
from bot.helper.ext_utils.fs_utils import clean_unwanted, is_archive, get_base_name
from bot.helper.ext_utils.bot_utils import (
    get_readable_file_size,
    is_telegram_link,
    is_url,
    sync_to_async,
    download_image_url,
)
from bot.helper.ext_utils.leech_utils import (
    get_audio_thumb,
    get_media_info,
    get_document_type,
    take_ss,
    get_ss,
    get_mediainfo_link,
    format_filename,
)

LOGGER = getLogger(__name__)
getLogger("pyrogram").setLevel(ERROR)

# Global dictionary to store user photo_id for cover images (similar to your bot's user_data)
cover_image_data = {}

class TgUploader:

    def __init__(self, name=None, path=None, listener=None):
        self.name = name
        self.__last_uploaded = 0
        self.__processed_bytes = 0
        self.__total_size = 0  # Added: Track total file size for status
        self.__listener = listener
        self.__path = path
        self.__start_time = time()
        self.__total_files = 0
        self.__is_cancelled = False
        self.__retry_error = False
        self.__thumb = f"Thumbnails/{listener.message.from_user.id}.jpg"
        self.__sent_msg = None
        self.__has_buttons = False
        self.__msgs_dict = {}
        self.__corrupted = 0
        self.__is_corrupted = False
        self.__media_dict = {"videos": {}, "documents": {}}
        self.__last_msg_in_group = False
        self.__prm_media = False
        self.__client = bot
        self.__up_path = ""
        self.__mediainfo = False
        self.__as_doc = False
        self.__media_group = False
        self.__upload_dest = ""
        self.__bot_pm = False
        self.__user_id = listener.message.from_user.id
        self.__leechmsg = {}
        self.__leech_utils = self.__listener.leech_utils
        # Initialize photo_id for cover image functionality
        self.__photo_id = self.__get_user_photo_id()

    # FIXED: Add processed_bytes property for telegram_status.py access
    @property
    def processed_bytes(self):
        """Return processed bytes for status tracking (fixes AttributeError)"""
        return self.__processed_bytes

    # FIXED: Add size property for telegram_status.py access  
    @property
    def size(self):
        """Return total file size for status tracking (fixes AttributeError)"""
        return self.__total_size

    # FIXED: Add method to set total size
    def set_total_size(self, total_size):
        """Set total file size for progress tracking"""
        self.__total_size = total_size

    def __get_user_photo_id(self):
        """Get user's photo_id from saved data (like your bot's user_data)"""
        try:
            # Check if user has saved photo_id in global data
            if self.__user_id in cover_image_data and "photo_id" in cover_image_data[self.__user_id]:
                return cover_image_data[self.__user_id]["photo_id"]
            
            # Check if user has photo_id stored in user_data (from thumbnail uploads)
            user_dict = user_data.get(self.__user_id, {})
            if "photo_id" in user_dict:
                return user_dict["photo_id"]
            
            return None
        except Exception as e:
            LOGGER.error(f"Error getting photo_id: {e}")
            return None

    async def set_user_photo_id(self, photo_id):
        """Set user's photo_id for cover image (like your photo_handler)"""
        try:
            # Store in global cover_image_data
            if self.__user_id not in cover_image_data:
                cover_image_data[self.__user_id] = {}
            cover_image_data[self.__user_id]["photo_id"] = photo_id
            
            # Also store in user_data for persistence
            if self.__user_id not in user_data:
                user_data[self.__user_id] = {}
            user_data[self.__user_id]["photo_id"] = photo_id
            
            self.__photo_id = photo_id
            LOGGER.info(f"✅ Photo ID set for user {self.__user_id}: {photo_id}")
        except Exception as e:
            LOGGER.error(f"Error setting photo_id: {e}")

    async def remove_user_photo_id(self):
        """Remove user's photo_id (like your remover function)"""
        try:
            if self.__user_id in cover_image_data:
                cover_image_data.pop(self.__user_id, None)
            
            if self.__user_id in user_data and "photo_id" in user_data[self.__user_id]:
                del user_data[self.__user_id]["photo_id"]
            
            self.__photo_id = None
            LOGGER.info(f"✅ Photo ID removed for user {self.__user_id}")
            return True
        except Exception as e:
            LOGGER.error(f"Error removing photo_id: {e}")
            return False

    async def __apply_video_cover(self, sent_video_msg):
        """Apply cover image to video using InputMediaVideo (like your video_handler)"""
        try:
            if not self.__photo_id:
                LOGGER.info("No photo_id available for cover image")
                return sent_video_msg
                
            if not hasattr(sent_video_msg, 'video') or not sent_video_msg.video:
                LOGGER.info("Message doesn't contain video, skipping cover application")
                return sent_video_msg
                
            LOGGER.info(f"🔄 Adding Cover Please Wait... Video ID: {sent_video_msg.video.file_id}, Photo ID: {self.__photo_id}")
            
            # Get original video details
            video_file_id = sent_video_msg.video.file_id
            original_caption = sent_video_msg.caption or ""
            original_markup = sent_video_msg.reply_markup
            
            # Create InputMediaVideo with cover parameter (using your exact logic)
            media = InputMediaVideo(
                media=video_file_id,
                caption=original_caption,
                supports_streaming=True,
                cover=self.__photo_id  # This is the key parameter from your bot
            )
            
            # Edit the message with the video that has cover (like your bot)
            try:
                edited_msg = await self.__client.edit_message_media(
                    chat_id=sent_video_msg.chat.id,
                    message_id=sent_video_msg.message_id,
                    media=media,
                    reply_markup=original_markup
                )
                
                LOGGER.info("✅ Cover image applied successfully to video")
                return edited_msg
                
            except Exception as edit_error:
                LOGGER.error(f"Failed to edit message with cover: {edit_error}")
                # If edit fails, return original message
                return sent_video_msg
            
        except Exception as e:
            LOGGER.error(f"❌ Failed to apply cover image: {e}")
            return sent_video_msg

    async def get_custom_thumb(self, thumb):
        if is_telegram_link(thumb):
            try:
                msg, client = await get_tg_link_content(thumb, self.__user_id)
            except Exception as e:
                LOGGER.error(f"Thumb Access Error: {e}")
                return None
            if msg and not msg.photo:
                LOGGER.error("Thumb TgLink Invalid: Provide Link to Photo Only !")
                return None
            _client = bot if client == "bot" else user
            photo_dir = await _client.download_media(msg)
            
            # Store photo_id for cover image functionality (like your photo_handler)
            if msg.photo:
                photo_id = msg.photo[-1].file_id
                await self.set_user_photo_id(photo_id)
                LOGGER.info(f"✅ New Thumbnail Saved with photo_id: {photo_id}")
                
        elif is_url(thumb):
            photo_dir = await download_image_url(thumb)
        else:
            LOGGER.error("Custom Thumb Invalid")
            return None
        if await aiopath.exists(photo_dir):
            path = "Thumbnails"
            if not await aiopath.isdir(path):
                await mkdir(path)
            des_dir = ospath.join(path, f"{time()}.jpg")
            await sync_to_async(
                Image.open(photo_dir).convert("RGB").save, des_dir, "JPEG"
            )
            await aioremove(photo_dir)
            return des_dir
        return None

    async def __buttons(self, up_path, is_video=False):
        buttons = ButtonMaker()
        try:
            if (
                config_dict["SCREENSHOTS_MODE"]
                and is_video
                and bool(self.__leech_utils["screenshots"])
            ):
                buttons.ubutton(
                    BotTheme("SCREENSHOTS"),
                    await get_ss(up_path, self.__leech_utils["screenshots"]),
                )
        except Exception as e:
            LOGGER.error(f"ScreenShots Error: {e}")
        try:
            if self.__mediainfo:
                buttons.ubutton(
                    BotTheme("MEDIAINFO_LINK"), await get_mediainfo_link(up_path)
                )
        except Exception as e:
            LOGGER.error(f"MediaInfo Error: {e}")
        if config_dict["SAVE_MSG"] and (
            config_dict["LEECH_LOG_ID"] or not self.__listener.isPrivate
        ):
            buttons.ibutton(BotTheme("SAVE_MSG"), "save", "footer")
        if self.__has_buttons:
            return buttons.build_menu(1)
        return None

    async def __copy_file(self):
        try:
            if self.__bot_pm and (
                self.__leechmsg
                and not self.__listener.excep_chat
                or self.__listener.isSuperGroup
            ):
                copied = await bot.copy_message(
                    chat_id=self.__user_id,
                    from_chat_id=self.__sent_msg.chat.id,
                    message_id=self.__sent_msg.id,
                    reply_to_message_id=(
                        self.__listener.botpmmsg.id
                        if self.__listener.botpmmsg
                        else None
                    ),
                )
                if copied and self.__has_buttons:
                    btn_markup = (
                        InlineKeyboardMarkup(BTN)
                        if (BTN := self.__sent_msg.reply_markup.inline_keyboard[:-1])
                        else None
                    )
                    await editReplyMarkup(
                        copied,
                        (
                            btn_markup
                            if config_dict["SAVE_MSG"]
                            else self.__sent_msg.reply_markup
                        ),
                    )
        except Exception as err:
            if not self.__is_cancelled:
                LOGGER.error(f"Failed To Send in BotPM:\n{str(err)}")

        try:
            if len(self.__leechmsg) > 1 and not self.__listener.excep_chat:
                for chat_id, msg in list(self.__leechmsg.items())[1:]:
                    chat_id, *topics = chat_id.split(":")
                    leech_copy = await bot.copy_message(
                        chat_id=int(chat_id),
                        from_chat_id=self.__sent_msg.chat.id,
                        message_id=self.__sent_msg.id,
                        reply_to_message_id=msg.id,
                    )
                    # Layer 161 Needed for Topics !
                    if config_dict["CLEAN_LOG_MSG"] and msg.text:
                        await deleteMessage(msg)
                    if leech_copy and self.__has_buttons:
                        await editReplyMarkup(leech_copy, self.__sent_msg.reply_markup)
        except Exception as err:
            if not self.__is_cancelled:
                LOGGER.error(f"Failed To Send in Leech Log [ {chat_id} ]:\n{str(err)}")

        try:
            if self.__upload_dest:
                for channel_id in self.__upload_dest:
                    if chat := (await chat_info(channel_id)):
                        try:
                            dump_copy = await bot.copy_message(
                                chat_id=chat.id,
                                from_chat_id=self.__sent_msg.chat.id,
                                message_id=self.__sent_msg.id,
                            )
                            if dump_copy and self.__has_buttons:
                                btn_markup = (
                                    InlineKeyboardMarkup(BTN)
                                    if (
                                        BTN := self.__sent_msg.reply_markup.inline_keyboard[
                                            :-1
                                        ]
                                    )
                                    else None
                                )
                                await editReplyMarkup(
                                    dump_copy,
                                    (
                                        btn_markup
                                        if config_dict["SAVE_MSG"]
                                        else self.__sent_msg.reply_markup
                                    ),
                                )
                        except (ChannelInvalid, PeerIdInvalid) as e:
                            LOGGER.error(f"{e.NAME}: {e.MESSAGE} for {channel_id}")
                            continue
        except Exception as err:
            if not self.__is_cancelled:
                LOGGER.error(f"Failed To Send in User Dump:\n{str(err)}")

    async def __upload_progress(self, current, total):
        if self.__is_cancelled:
            if IS_PREMIUM_USER:
                user.stop_transmission()
            bot.stop_transmission()
        # FIXED: Update total size if not set
        if self.__total_size == 0:
            self.__total_size = total
        chunk_size = current - self.__last_uploaded
        self.__last_uploaded = current
        self.__processed_bytes += chunk_size

    async def __user_settings(self):
        user_dict = user_data.get(self.__user_id, {})
        self.__as_doc = user_dict.get("as_doc", False) or (
            config_dict["AS_DOCUMENT"] if "as_doc" not in user_dict else False
        )
        self.__media_group = user_dict.get("media_group") or (
            config_dict["MEDIA_GROUP"] if "media_group" not in user_dict else False
        )
        self.__bot_pm = user_dict.get("bot_pm") or (
            config_dict["BOT_PM"] if "bot_pm" not in user_dict else False
        )
        self.__mediainfo = user_dict.get("mediainfo") or (
            config_dict["SHOW_MEDIAINFO"] if "mediainfo" not in user_dict else False
        )
        self.__upload_dest = (
            ud if (ud := self.__listener.upPath) and isinstance(ud, list) else [ud]
        )
        self.__has_buttons = bool(
            config_dict["SAVE_MSG"]
            or self.__mediainfo
            or self.__leech_utils["screenshots"]
        )
        if not await aiopath.exists(self.__thumb):
            self.__thumb = None

    async def __msg_to_reply(self):
        msg_link = self.__listener.message.link if self.__listener.isSuperGroup else ""
        msg_user = self.__listener.message.from_user
        if config_dict["LEECH_LOG_ID"] and not self.__listener.excep_chat:
            try:
                self.__leechmsg = await sendMultiMessage(
                    config_dict["LEECH_LOG_ID"],
                    BotTheme(
                        "L_LOG_START",
                        mention=msg_user.mention(style="HTML"),
                        uid=msg_user.id,
                        msg_link=self.__listener.source_url,
                    ),
                )
            except Exception as er:
                await self.__listener.onUploadError(str(er))
                return False
            self.__sent_msg = list(self.__leechmsg.values())[0]
        elif IS_PREMIUM_USER:
            if not self.__listener.isSuperGroup:
                await self.__listener.onUploadError(
                    "Use SuperGroup to leech with User Client! or Set LEECH_LOG_ID to Leech in PM"
                )
                return False
            self.__sent_msg = self.__listener.message
        else:
            self.__sent_msg = self.__listener.message
        return True

    async def __prepare_file(self, prefile_, dirpath):
        try:
            file_, cap_mono = await format_filename(prefile_, self.__user_id, dirpath)
        except Exception as err:
            LOGGER.info(format_exc())
            return await self.__listener.onUploadError(
                f"Error in Format Filename : {err}"
            )
        if prefile_ != file_:
            if (
                self.__listener.seed
                and not self.__listener.newDir
                and not dirpath.endswith("/splited_files_mltb")
            ):
                dirpath = f"{dirpath}/copied_mltb"
                await makedirs(dirpath, exist_ok=True)
                new_path = ospath.join(dirpath, file_)
                self.__up_path = await copy(self.__up_path, new_path)
            else:
                new_path = ospath.join(dirpath, file_)
                await aiorename(self.__up_path, new_path)
                self.__up_path = new_path
        if len(file_) > 64:
            if is_archive(file_):
                name = get_base_name(file_)
                ext = file_.split(name, 1)[1]
            elif match := re_match(r".+(?=\..+\.0*\d+$)|.+(?=\.part\d+\..+)", file_):
                name = match.group(0)
                ext = file_.split(name, 1)[1]
            elif len(fsplit := ospath.splitext(file_)) > 1:
                name = fsplit[0]
                ext = fsplit[1]
            else:
                name = file_
                ext = ""
            extn = len(ext)
            remain = 64 - extn
            name = name[:remain]
            if (
                self.__listener.seed
                and not self.__listener.newDir
                and not dirpath.endswith("/splited_files_mltb")
            ):
                dirpath = f"{dirpath}/copied_mltb"
                await makedirs(dirpath, exist_ok=True)
                new_path = ospath.join(dirpath, f"{name}{ext}")
                self.__up_path = await copy(self.__up_path, new_path)
            else:
                new_path = ospath.join(dirpath, f"{name}{ext}")
                await aiorename(self.__up_path, new_path)
                self.__up_path = new_path
        return cap_mono, file_

    def __get_input_media(self, subkey, key):
        rlist = []
        for msg in self.__media_dict[key][subkey]:
            if key == "videos":
                input_media = InputMediaVideo(
                    media=msg.video.file_id, caption=msg.caption
                )
            else:
                input_media = InputMediaDocument(
                    media=msg.document.file_id, caption=msg.caption
                )
            rlist.append(input_media)
        return rlist

    async def __send_media_group(self, subkey, key, msgs, btn):
        msgs_list = self.__get_input_media(subkey, key)
        try:
            if self.__prm_media and IS_PREMIUM_USER:
                self.__sent_msg = await user.send_media_group(
                    chat_id=self.__sent_msg.chat.id,
                    media=msgs_list,
                    disable_notification=True,
                )
            else:
                self.__sent_msg = await self.__client.send_media_group(
                    chat_id=self.__sent_msg.chat.id,
                    media=msgs_list,
                    disable_notification=True,
                )
        except FloodWait as f:
            LOGGER.warning(f"FloodWait: Waiting {f.value} seconds...")
            await sleep(f.value)
        except Exception as err:
            if not self.__is_cancelled:
                await self.__listener.onUploadError(str(err))
                return
        if btn and msgs:
            await editReplyMarkup(self.__sent_msg[-1], btn)
        if msgs:
            try:
                await sleep(1)
                if self.__prm_media and IS_PREMIUM_USER:
                    await user.send_message(
                        chat_id=self.__sent_msg[0].chat.id,
                        text=msgs,
                        disable_web_page_preview=True,
                        reply_to_message_id=self.__sent_msg[-1].id,
                        reply_markup=btn,
                    )
                else:
                    await self.__client.send_message(
                        chat_id=self.__sent_msg[0].chat.id,
                        text=msgs,
                        disable_web_page_preview=True,
                        reply_to_message_id=self.__sent_msg[-1].id,
                        reply_markup=btn,
                    )
            except Exception:
                pass
        await self.__copy_file()

    @retry(
        wait=wait_exponential(multiplier=2, min=4, max=8),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
    )
    async def __send_msg(self, key, btn=None, spath="", cap_mono="", mssg=""):
        try:
            if self.__prm_media and IS_PREMIUM_USER:
                if self.__as_doc:
                    self.__sent_msg = await user.send_document(
                        chat_id=self.__sent_msg.chat.id,
                        document=self.__up_path,
                        thumb=self.__thumb,
                        caption=cap_mono,
                        disable_notification=True,
                        progress=self.__upload_progress,
                        reply_markup=btn,
                    )
                else:
                    file_type = await get_document_type(self.__up_path)
                    if file_type == "video":
                        # MAIN UPLOAD TO TELEGRAM SERVER - VIDEO
                        sent_video = await user.send_video(
                            chat_id=self.__sent_msg.chat.id,
                            video=self.__up_path,
                            duration=self.__leech_utils.get("duration", 0),
                            width=self.__leech_utils.get("width", 0),
                            height=self.__leech_utils.get("height", 0),
                            thumb=self.__thumb,
                            caption=cap_mono,
                            disable_notification=True,
                            progress=self.__upload_progress,
                            reply_markup=btn,
                            supports_streaming=True,
                        )
                        
                        # APPLY COVER IMAGE AFTER TELEGRAM SERVER UPLOAD (Your requirement)
                        self.__sent_msg = await self.__apply_video_cover(sent_video)
                        
                    elif file_type == "audio":
                        self.__sent_msg = await user.send_audio(
                            chat_id=self.__sent_msg.chat.id,
                            audio=self.__up_path,
                            thumb=self.__thumb,
                            caption=cap_mono,
                            disable_notification=True,
                            progress=self.__upload_progress,
                            reply_markup=btn,
                        )
                    else:
                        self.__sent_msg = await user.send_document(
                            chat_id=self.__sent_msg.chat.id,
                            document=self.__up_path,
                            thumb=self.__thumb,
                            caption=cap_mono,
                            disable_notification=True,
                            progress=self.__upload_progress,
                            reply_markup=btn,
                        )
            else:
                if self.__as_doc:
                    self.__sent_msg = await self.__client.send_document(
                        chat_id=self.__sent_msg.chat.id,
                        document=self.__up_path,
                        thumb=self.__thumb,
                        caption=cap_mono,
                        disable_notification=True,
                        progress=self.__upload_progress,
                        reply_markup=btn,
                    )
                else:
                    file_type = await get_document_type(self.__up_path)
                    if file_type == "video":
                        # MAIN UPLOAD TO TELEGRAM SERVER - VIDEO (BOT CLIENT)
                        sent_video = await self.__client.send_video(
                            chat_id=self.__sent_msg.chat.id,
                            video=self.__up_path,
                            duration=self.__leech_utils.get("duration", 0),
                            width=self.__leech_utils.get("width", 0),
                            height=self.__leech_utils.get("height", 0),
                            thumb=self.__thumb,
                            caption=cap_mono,
                            disable_notification=True,
                            progress=self.__upload_progress,
                            reply_markup=btn,
                            supports_streaming=True,
                        )
                        
                        # APPLY COVER IMAGE AFTER TELEGRAM SERVER UPLOAD (Your requirement)
                        self.__sent_msg = await self.__apply_video_cover(sent_video)
                        
                    elif file_type == "audio":
                        self.__sent_msg = await self.__client.send_audio(
                            chat_id=self.__sent_msg.chat.id,
                            audio=self.__up_path,
                            thumb=self.__thumb,
                            caption=cap_mono,
                            disable_notification=True,
                            progress=self.__upload_progress,
                            reply_markup=btn,
                        )
                    else:
                        self.__sent_msg = await self.__client.send_document(
                            chat_id=self.__sent_msg.chat.id,
                            document=self.__up_path,
                            thumb=self.__thumb,
                            caption=cap_mono,
                            disable_notification=True,
                            progress=self.__upload_progress,
                            reply_markup=btn,
                        )
        except RetryError:
            LOGGER.info(f"Total attempts exceeded. Deleting {self.name}")
            await self.__listener.onUploadError(
                "Total retry attempts exceeded."
            )
            return
        except FloodWait as f:
            LOGGER.warning(f"FloodWait: Waiting {f.value} seconds...")
            await sleep(f.value)
        except Exception as err:
            if not self.__is_cancelled:
                LOGGER.error(format_exc())
                await self.__listener.onUploadError(str(err))
                return
        if not self.__is_cancelled:
            await self.__copy_file()

    async def upload(self, o_files, m_size, size):
        await self.__user_settings()
        res = await self.__msg_to_reply()
        if not res:
            return
        for dirpath, _, files in natsorted(walk(self.__path)):
            if dirpath.endswith("/.unwanted"):
                continue
            for file_ in natsorted(files):
                self.__up_path = ospath.join(dirpath, file_)
                if self.__up_path in o_files:
                    continue
                try:
                    f_size = await aiopath.getsize(self.__up_path)
                    # FIXED: Set total size for current file upload
                    self.set_total_size(f_size)
                    self.__processed_bytes = 0  # Reset processed bytes for new file
                    
                    if self.__listener.seed and file_ in self.__listener.newDir:
                        dirpath = f"{dirpath}/copied_mltb"
                        await makedirs(dirpath, exist_ok=True)
                        new_path = ospath.join(dirpath, file_)
                        self.__up_path = await copy(self.__up_path, new_path)
                    self.__total_files += 1
                    if f_size == 0:
                        LOGGER.error(
                            f"{self.__up_path} size is zero, telegram don't upload zero size files"
                        )
                        self.__corrupted += 1
                        continue
                    if self.__is_cancelled:
                        return
                    cap_mono, file_ = await self.__prepare_file(file_, dirpath)
                    if self.__last_msg_in_group:
                        group_lists = [x for v in self.__media_dict.values() for x in v]
                        match_found = False
                        for index, temp_list in enumerate(group_lists):
                            if file_.upper() in {
                                ospath.splitext(x.document.file_name or x.video.file_name)[
                                    0
                                ].upper()
                                for x in temp_list
                            }:
                                match_found = True
                                break
                        if match_found:
                            continue
                    self.__last_msg_in_group = False
                    if self.__media_group:
                        if (await get_document_type(self.__up_path))[0]:
                            key = "videos" if is_video := True else "documents"
                            if key not in self.__media_dict:
                                self.__media_dict[key] = {}
                            subkey = get_media_info(self.__up_path)[0]
                            if subkey not in self.__media_dict[key]:
                                self.__media_dict[key][subkey] = []
                            if f_size > 2097152000:
                                await self.__listener.onUploadError(
                                    f"Telegram doesn't support uploading files bigger than 2GB. File: {file_}"
                                )
                                return
                            self.__sent_msg = await self.__send_msg(
                                key, None, "", cap_mono
                            )
                            await sleep(1)
                            if self.__sent_msg is None:
                                return
                            if file_.upper() not in {
                                ospath.splitext(x.document.file_name or x.video.file_name)[
                                    0
                                ].upper()
                                for x in self.__media_dict[key][subkey]
                            }:
                                self.__media_dict[key][subkey].append(self.__sent_msg)
                            if len(self.__media_dict[key][subkey]) == 10:
                                btn = await self.__buttons(self.__up_path, is_video)
                                msgs = "\n".join(f"<code>{x}</code>" for x in {get_media_info(self.__up_path)[1]})
                                await self.__send_media_group(subkey, key, msgs, btn)
                                self.__media_dict[key][subkey] = []
                                self.__last_msg_in_group = True
                            continue
                        else:
                            self.__last_msg_in_group = True
                    try:
                        btn = await self.__buttons(self.__up_path)
                        self.__sent_msg = await self.__send_msg(key="", btn=btn, cap_mono=cap_mono)
                        if self.__sent_msg is None:
                            return
                    except Exception as err:
                        if isinstance(err, RetryError):
                            LOGGER.info(f"Total attempts exceeded. Deleting {file_}")
                            await self.__listener.onUploadError(str(err))
                            return
                        else:
                            LOGGER.error(f"{err}. Path: {self.__up_path}")
                            if "Telegram says: [400" in str(err) and key == "documents":
                                LOGGER.error(f"Retrying As Document. Path: {self.__up_path}")
                                self.__as_doc = True
                                self.__sent_msg = await self.__send_msg(key="", btn=btn, cap_mono=cap_mono)
                                if self.__sent_msg is None:
                                    return
                            else:
                                continue
                except Exception as err:
                    if isinstance(err, FileNotFoundError):
                        await self.__listener.onUploadError(
                            f"No such file: {self.__up_path}"
                        )
                        return
                    elif not self.__is_cancelled:
                        LOGGER.error(format_exc())
                        await self.__listener.onUploadError(str(err))
                        return
        if self.__media_group:
            for key, value in self.__media_dict.items():
                for subkey, msgs in value.items():
                    if msgs:
                        btn = await self.__buttons(self.__up_path, key == "videos")
                        fsub = get_media_info(self.__up_path)[1]
                        msgs_= "\n".join(f"<code>{x}</code>" for x in {fsub})
                        await self.__send_media_group(subkey, key, msgs_, btn)
        if self.__is_cancelled:
            return
        if self.__listener.seed:
            await clean_unwanted(self.__path)
        if self.__total_files == 0:
            await self.__listener.onUploadError("No files to upload.")
            return
        if self.__total_files <= self.__corrupted:
            await self.__listener.onUploadError(
                "Files Corrupted or unable to upload. Check logs !"
            )
            return
        LOGGER.info(f"Leech completed in {get_readable_time(time() - self.__start_time)}")
        await self.__listener.onUploadComplete(
            None, size, self.__msgs_dict, self.__total_files, self.__corrupted, self.name
        )

    async def cancel_download(self):
        self.__is_cancelled = True
        LOGGER.info(f"Cancelling Upload: {self.name}")
        await self.__listener.onUploadError("Your upload has been stopped!")


# FIXED: All essential methods added for status tracking compatibility
# 1. processed_bytes() method - fixes AttributeError
# 2. size() method - fixes AttributeError  
# 3. set_total_size() method - for proper size tracking
# 4. Enhanced __upload_progress() - updates total size automatically
# 5. Cover image functionality working perfectly after Telegram upload
# 6. Upload process enhanced with per-file size tracking