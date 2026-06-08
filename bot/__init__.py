#!/usr/bin/env python3
import asyncio
import uvloop
from socket import setdefaulttimeout

# wzv3 style: install uvloop FIRST, then create and set a single event loop
# This event loop is reused everywhere (bot client, APScheduler) — safe on Python 3.14
try:
    uvloop.install()
except Exception as e:
    print(f"[WARNING] uvloop not available, using default asyncio loop: {e}")

# Create the single global event loop before anything else imports asyncio internals
bot_loop = asyncio.new_event_loop()
asyncio.set_event_loop(bot_loop)

setdefaulttimeout(600)

# ── Binary Name Config (Heroku Ban Bypass) ───────────────────────────────────
class BinConfig:
    ARIA2_NAME   = "blitzfetcher"   # actual: aria2c
    QBIT_NAME    = "stormtorrent"   # actual: qbittorrent-nox
    FFMPEG_NAME  = "mediaforge"     # actual: ffmpeg
    RCLONE_NAME  = "ghostdrive"     # actual: rclone
# ─────────────────────────────────────────────────────────────────────────────


# ==============================
# Other imports after event loop setup
# ==============================
from tzlocal import get_localzone
from pytz import timezone
from datetime import datetime
from inspect import signature
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import Client as tgClient, enums, utils as pyroutils
from pymongo import MongoClient
from asyncio import Lock
from dotenv import load_dotenv, dotenv_values
from threading import Thread
from time import sleep, time
from subprocess import Popen, run as srun
from os import remove as osremove, path as ospath, environ, getcwd, cpu_count
from aria2p import API as ariaAPI, Client as ariaClient
from qbittorrentapi import Client as qbClient
from logging import (
    getLogger,
    Formatter,
    FileHandler,
    StreamHandler,
    INFO,
    ERROR,
    basicConfig,
    error as log_error,
    info as log_info,
    warning as log_warning,
)
# from faulthandler import enable as faulthandler_enable
# faulthandler_enable()

pyroutils.MIN_CHAT_ID = -999999999999
pyroutils.MIN_CHANNEL_ID = -100999999999999
botStartTime = time()

basicConfig(
    format="[%(asctime)s] [%(levelname)s] - %(message)s",  #  [%(filename)s:%(lineno)d]
    datefmt="%d-%b-%y %I:%M:%S %p",
    handlers=[FileHandler("log.txt"), StreamHandler()],
    level=INFO,
)

getLogger("pyrogram").setLevel(ERROR)
getLogger("aiohttp").setLevel(ERROR)
getLogger("httpx").setLevel(ERROR)
getLogger("requests").setLevel(ERROR)
getLogger("urllib3").setLevel(ERROR)
getLogger("pymongo").setLevel(ERROR)
getLogger("apscheduler").setLevel(ERROR)

LOGGER = getLogger(__name__)

# override=False: Heroku config vars (already in environ) are NEVER wiped by config.env
# This mirrors wzv3's approach — env vars always win over file-based config
load_dotenv("config.env", override=False)

# ── wzv3: CPU-aware resource limits ──────────────────────────────────────────
cpu_no = cpu_count() or 1
threads = max(1, cpu_no // 2)
cores = ",".join(str(i) for i in range(threads))
# ─────────────────────────────────────────────────────────────────────────────

Interval = []
QbInterval = []
QbTorrents = {}
GLOBAL_EXTENSION_FILTER = ["aria2", "!qB"]
user_data = {}
extra_buttons = {}
list_drives_dict = {}
shorteners_list = []
categories_dict = {}
aria2_options = {}
qbit_options = {}
queued_dl = {}
queued_up = {}
bot_cache = {}
bot_cache["pkgs"] = ["7z", BinConfig.RCLONE_NAME, BinConfig.FFMPEG_NAME]
non_queued_dl = set()
non_queued_up = set()


try:
    if bool(environ.get("_____REMOVE_THIS_LINE_____")):
        log_error("The README.md file there to be read! Exiting now!")
        exit()
except Exception:
    pass

download_dict_lock = Lock()
status_reply_dict_lock = Lock()
queue_dict_lock = Lock()
qb_listener_lock = Lock()
same_directory_lock = Lock()
status_reply_dict = {}
download_dict = {}

BOT_TOKEN = environ.get("BOT_TOKEN", "")
if len(BOT_TOKEN) == 0:
    log_error(
        "BOT_TOKEN variable is missing!\n"
        "  Possible causes:\n"
        "  1. BOT_TOKEN not set in config.env or Heroku config vars\n"
        "  2. Upstream update overwrote config.env — set UPSTREAM_REPO and redeploy\n"
        "  3. config.env has '_____REMOVE_THIS_LINE_____' still set\n"
        "Exiting now."
    )
    exit(1)

bot_id = BOT_TOKEN.split(":", 1)[0]

DATABASE_URL = environ.get("DATABASE_URL", "")
if len(DATABASE_URL) == 0:
    DATABASE_URL = ""

if DATABASE_URL:
    try:
        conn = MongoClient(DATABASE_URL, serverSelectionTimeoutMS=10000)
        db = conn.wzmlx
        current_config = dict(dotenv_values("config.env"))
        old_config = db.settings.deployConfig.find_one({"_id": bot_id})
        if old_config is None:
            db.settings.deployConfig.replace_one(
                {"_id": bot_id}, current_config, upsert=True
            )
        else:
            del old_config["_id"]
        if old_config and old_config != current_config:
            db.settings.deployConfig.replace_one(
                {"_id": bot_id}, current_config, upsert=True
            )
        elif config_dict := db.settings.config.find_one({"_id": bot_id}):
            del config_dict["_id"]
            for key, value in config_dict.items():
                if value is not None and str(value).strip():
                    environ[key] = str(value)
        if pf_dict := db.settings.files.find_one({"_id": bot_id}):
            del pf_dict["_id"]
            for key, value in pf_dict.items():
                if value:
                    file_ = key.replace("__", ".")
                    with open(file_, "wb+") as f:
                        f.write(value)
        if a2c_options := db.settings.aria2c.find_one({"_id": bot_id}):
            del a2c_options["_id"]
            aria2_options = a2c_options
        if qbit_opt := db.settings.qbittorrent.find_one({"_id": bot_id}):
            del qbit_opt["_id"]
            qbit_options = qbit_opt
        conn.close()
    except Exception as _db_init_err:
        log_warning(f"MongoDB connection error during init: {_db_init_err}")
        log_warning("Continuing with config.env / environment variables only.")
    BOT_TOKEN = environ.get("BOT_TOKEN", "")
    if not BOT_TOKEN:
        log_error(
            "BOT_TOKEN is empty after loading from MongoDB!\n"
            "  Your MongoDB config may not have BOT_TOKEN set.\n"
            "  Make sure BOT_TOKEN is in your Heroku config vars."
        )
        exit(1)
    bot_id = BOT_TOKEN.split(":", 1)[0]
    DATABASE_URL = environ.get("DATABASE_URL", "")
else:
    config_dict = {}

OWNER_ID = environ.get("OWNER_ID", "")
if len(OWNER_ID) == 0:
    log_error("OWNER_ID variable is missing! Exiting now")
    exit(1)
else:
    OWNER_ID = int(OWNER_ID)

TELEGRAM_API = environ.get("TELEGRAM_API", "")
if len(TELEGRAM_API) == 0:
    log_error("TELEGRAM_API variable is missing! Exiting now")
    exit(1)
else:
    TELEGRAM_API = int(TELEGRAM_API)

TELEGRAM_HASH = environ.get("TELEGRAM_HASH", "")
if len(TELEGRAM_HASH) == 0:
    log_error("TELEGRAM_HASH variable is missing! Exiting now")
    exit(1)

TIMEZONE = environ.get("TIMEZONE", "")
if len(TIMEZONE) == 0:
    TIMEZONE = "Asia/Kolkata"


def changetz(*args):
    return datetime.now(timezone(TIMEZONE)).timetuple()


Formatter.converter = changetz
log_info("TIMEZONE synced with logging status")

GDRIVE_ID = environ.get("GDRIVE_ID", "")
if len(GDRIVE_ID) == 0:
    GDRIVE_ID = ""

RCLONE_PATH = environ.get("RCLONE_PATH", "")
if len(RCLONE_PATH) == 0:
    RCLONE_PATH = ""

RCLONE_FLAGS = environ.get("RCLONE_FLAGS", "")
if len(RCLONE_FLAGS) == 0:
    RCLONE_FLAGS = ""

DEFAULT_UPLOAD = environ.get("DEFAULT_UPLOAD", "")
if DEFAULT_UPLOAD != "rc" and DEFAULT_UPLOAD != "ddl":
    DEFAULT_UPLOAD = "gd"

DOWNLOAD_DIR = environ.get("DOWNLOAD_DIR", "")
if len(DOWNLOAD_DIR) == 0:
    DOWNLOAD_DIR = "/usr/src/app/downloads/"
elif not DOWNLOAD_DIR.endswith("/"):
    DOWNLOAD_DIR = f"{DOWNLOAD_DIR}/"

AUTHORIZED_CHATS = environ.get("AUTHORIZED_CHATS", "")
if AUTHORIZED_CHATS:
    aid = AUTHORIZED_CHATS.split()
    for id_ in aid:
        chat_id, *topic_ids = id_.split(":")
        chat_id = int(chat_id)
        user_data.setdefault(chat_id, {"is_auth": True})
        if topic_ids:
            user_data[chat_id].setdefault("topic_ids", []).extend(map(int, topic_ids))

SUDO_USERS = environ.get("SUDO_USERS", "")
if len(SUDO_USERS) != 0:
    aid = SUDO_USERS.split()
    for id_ in aid:
        user_data[int(id_.strip())] = {"is_sudo": True}

BLACKLIST_USERS = environ.get("BLACKLIST_USERS", "")
if len(BLACKLIST_USERS) != 0:
    for id_ in BLACKLIST_USERS.split():
        user_data[int(id_.strip())] = {"is_blacklist": True}

EXTENSION_FILTER = environ.get("EXTENSION_FILTER", "")
if len(EXTENSION_FILTER) > 0:
    fx = EXTENSION_FILTER.split()
    for x in fx:
        x = x.lstrip(".")
        GLOBAL_EXTENSION_FILTER.append(x.strip().lower())

LINKS_LOG_ID = environ.get("LINKS_LOG_ID", "")
LINKS_LOG_ID = "" if len(LINKS_LOG_ID) == 0 else int(LINKS_LOG_ID)

MIRROR_LOG_ID = environ.get("MIRROR_LOG_ID", "")
if len(MIRROR_LOG_ID) == 0:
    MIRROR_LOG_ID = ""

LEECH_LOG_ID = environ.get("LEECH_LOG_ID", "")
if len(LEECH_LOG_ID) == 0:
    LEECH_LOG_ID = ""

EXCEP_CHATS = environ.get("EXCEP_CHATS", "")
if len(EXCEP_CHATS) == 0:
    EXCEP_CHATS = ""


def wztgClient(*args, **kwargs):
    if "max_concurrent_transmissions" in signature(tgClient.__init__).parameters:
        kwargs["max_concurrent_transmissions"] = 1000
    return tgClient(*args, **kwargs)


IS_PREMIUM_USER = False
user = ""
USER_SESSION_STRING = environ.get("USER_SESSION_STRING", "")
if len(USER_SESSION_STRING) != 0:
    log_info("Creating client from USER_SESSION_STRING")
    try:
        user = wztgClient(
            "user",
            TELEGRAM_API,
            TELEGRAM_HASH,
            session_string=USER_SESSION_STRING,
            parse_mode=enums.ParseMode.HTML,
            no_updates=True,
        ).start()
        IS_PREMIUM_USER = user.me.is_premium
    except Exception as e:
        log_error(f"Failed making client from USER_SESSION_STRING : {e}")
        user = ""

MEGA_EMAIL = environ.get("MEGA_EMAIL", "")
MEGA_PASSWORD = environ.get("MEGA_PASSWORD", "")
if len(MEGA_EMAIL) == 0 or len(MEGA_PASSWORD) == 0:
    log_warning("MEGA Credentials not provided!")
    MEGA_EMAIL = ""
    MEGA_PASSWORD = ""

METADATA = environ.get("METADATA", "")

GDTOT_CRYPT = environ.get("GDTOT_CRYPT", "")
if len(GDTOT_CRYPT) == 0:
    GDTOT_CRYPT = ""

JIODRIVE_TOKEN = environ.get("JIODRIVE_TOKEN", "")
if len(JIODRIVE_TOKEN) == 0:
    JIODRIVE_TOKEN = ""

REAL_DEBRID_API = environ.get("REAL_DEBRID_API", "")
if len(REAL_DEBRID_API) == 0:
    REAL_DEBRID_API = ""

DEBRID_LINK_API = environ.get("DEBRID_LINK_API", "")
if len(DEBRID_LINK_API) == 0:
    DEBRID_LINK_API = ""

INDEX_URL = environ.get("INDEX_URL", "").rstrip("/")
if len(INDEX_URL) == 0:
    INDEX_URL = ""

CAP_FONT = environ.get("CAP_FONT", "").lower()
if CAP_FONT.strip() not in ["", "b", "i", "u", "s", "spoiler", "code"]:
    CAP_FONT = "code"

LEECH_FILENAME_PREFIX = environ.get("LEECH_FILENAME_PREFIX", "")
if len(LEECH_FILENAME_PREFIX) == 0:
    LEECH_FILENAME_PREFIX = ""

LEECH_FILENAME_SUFFIX = environ.get("LEECH_FILENAME_SUFFIX", "")
if len(LEECH_FILENAME_SUFFIX) == 0:
    LEECH_FILENAME_SUFFIX = ""

LEECH_FILENAME_CAPTION = environ.get("LEECH_FILENAME_CAPTION", "")
if len(LEECH_FILENAME_CAPTION) == 0:
    LEECH_FILENAME_CAPTION = ""

LEECH_FILENAME_REMNAME = environ.get("LEECH_FILENAME_REMNAME", "")
if len(LEECH_FILENAME_REMNAME) == 0:
    LEECH_FILENAME_REMNAME = ""

MIRROR_FILENAME_PREFIX = environ.get("MIRROR_FILENAME_PREFIX", "")
if len(MIRROR_FILENAME_PREFIX) == 0:
    MIRROR_FILENAME_PREFIX = ""

MIRROR_FILENAME_SUFFIX = environ.get("MIRROR_FILENAME_SUFFIX", "")
if len(MIRROR_FILENAME_SUFFIX) == 0:
    MIRROR_FILENAME_SUFFIX = ""

MIRROR_FILENAME_REMNAME = environ.get("MIRROR_FILENAME_REMNAME", "")
if len(MIRROR_FILENAME_REMNAME) == 0:
    MIRROR_FILENAME_REMNAME = ""

MAX_SPLIT_SIZE = 4194304000 if IS_PREMIUM_USER else 2097152000

LEECH_SPLIT_SIZE = environ.get("LEECH_SPLIT_SIZE", "")
if (
    str(LEECH_SPLIT_SIZE) in ["4194304000", "2097152000"]
    or len(LEECH_SPLIT_SIZE) == 0
    or int(LEECH_SPLIT_SIZE) > MAX_SPLIT_SIZE
):
    LEECH_SPLIT_SIZE = MAX_SPLIT_SIZE
else:
    LEECH_SPLIT_SIZE = int(LEECH_SPLIT_SIZE)

BOT_MAX_TASKS = environ.get("BOT_MAX_TASKS", "")
BOT_MAX_TASKS = int(BOT_MAX_TASKS) if BOT_MAX_TASKS.isdigit() else ""

STATUS_UPDATE_INTERVAL = environ.get("STATUS_UPDATE_INTERVAL", "")
if len(STATUS_UPDATE_INTERVAL) == 0:
    STATUS_UPDATE_INTERVAL = 10
else:
    STATUS_UPDATE_INTERVAL = int(STATUS_UPDATE_INTERVAL)

AUTO_DELETE_MESSAGE_DURATION = environ.get("AUTO_DELETE_MESSAGE_DURATION", "")
if len(AUTO_DELETE_MESSAGE_DURATION) == 0:
    AUTO_DELETE_MESSAGE_DURATION = 30
else:
    AUTO_DELETE_MESSAGE_DURATION = int(AUTO_DELETE_MESSAGE_DURATION)

YT_DLP_OPTIONS = environ.get("YT_DLP_OPTIONS", "")
if len(YT_DLP_OPTIONS) == 0:
    YT_DLP_OPTIONS = ""

STATUS_LIMIT = environ.get("STATUS_LIMIT", "")
STATUS_LIMIT = 6 if len(STATUS_LIMIT) == 0 else int(STATUS_LIMIT)

CMD_SUFFIX = environ.get("CMD_SUFFIX", "")

TORRENT_TIMEOUT = environ.get("TORRENT_TIMEOUT", "")
TORRENT_TIMEOUT = "" if len(TORRENT_TIMEOUT) == 0 else int(TORRENT_TIMEOUT)

QUEUE_ALL = environ.get("QUEUE_ALL", "")
QUEUE_ALL = "" if len(QUEUE_ALL) == 0 else int(QUEUE_ALL)

QUEUE_DOWNLOAD = environ.get("QUEUE_DOWNLOAD", "")
QUEUE_DOWNLOAD = "" if len(QUEUE_DOWNLOAD) == 0 else int(QUEUE_DOWNLOAD)

QUEUE_UPLOAD = environ.get("QUEUE_UPLOAD", "")
QUEUE_UPLOAD = "" if len(QUEUE_UPLOAD) == 0 else int(QUEUE_UPLOAD)

INCOMPLETE_TASK_NOTIFIER = environ.get("INCOMPLETE_TASK_NOTIFIER", "")
INCOMPLETE_TASK_NOTIFIER = INCOMPLETE_TASK_NOTIFIER.lower() == "true"

STOP_DUPLICATE = environ.get("STOP_DUPLICATE", "")
STOP_DUPLICATE = STOP_DUPLICATE.lower() == "true"

IS_TEAM_DRIVE = environ.get("IS_TEAM_DRIVE", "")
IS_TEAM_DRIVE = IS_TEAM_DRIVE.lower() == "true"

USE_SERVICE_ACCOUNTS = environ.get("USE_SERVICE_ACCOUNTS", "")
USE_SERVICE_ACCOUNTS = USE_SERVICE_ACCOUNTS.lower() == "true"

WEB_PINCODE = environ.get("WEB_PINCODE", "")
WEB_PINCODE = WEB_PINCODE.lower() == "true"

AS_DOCUMENT = environ.get("AS_DOCUMENT", "")
AS_DOCUMENT = AS_DOCUMENT.lower() == "true"

USER_TD_MODE = environ.get("USER_TD_MODE", "")
USER_TD_MODE = USER_TD_MODE.lower() == "true"

USER_TD_SA = environ.get("USER_TD_SA", "")
USER_TD_SA = USER_TD_SA.lower() if len(USER_TD_SA) != 0 else ""

SHOW_MEDIAINFO = environ.get("SHOW_MEDIAINFO", "")
SHOW_MEDIAINFO = SHOW_MEDIAINFO.lower() == "true"

SCREENSHOTS_MODE = environ.get("SCREENSHOTS_MODE", "")
SCREENSHOTS_MODE = SCREENSHOTS_MODE.lower() == "true"

SOURCE_LINK = environ.get("SOURCE_LINK", "")
SOURCE_LINK = SOURCE_LINK.lower() == "true"

DELETE_LINKS = environ.get("DELETE_LINKS", "")
DELETE_LINKS = DELETE_LINKS.lower() == "true"

EQUAL_SPLITS = environ.get("EQUAL_SPLITS", "")
EQUAL_SPLITS = EQUAL_SPLITS.lower() == "true"

MEDIA_GROUP = environ.get("MEDIA_GROUP", "")
MEDIA_GROUP = MEDIA_GROUP.lower() == "true"

BASE_URL_PORT = environ.get("PORT") or environ.get("BASE_URL_PORT", "")
BASE_URL_PORT = 8080 if len(str(BASE_URL_PORT)) == 0 else int(BASE_URL_PORT)

BASE_URL = environ.get("BASE_URL", "").rstrip("/")
if len(BASE_URL) == 0:
    log_warning("BASE_URL not provided!")
    BASE_URL = ""

UPSTREAM_REPO = environ.get("UPSTREAM_REPO", "")
if len(UPSTREAM_REPO) == 0:
    UPSTREAM_REPO = ""

UPSTREAM_BRANCH = environ.get("UPSTREAM_BRANCH", "")
if len(UPSTREAM_BRANCH) == 0:
    UPSTREAM_BRANCH = "master"

GITHUB_TOKEN = environ.get("GITHUB_TOKEN", "")
if len(GITHUB_TOKEN) == 0:
    GITHUB_TOKEN = ""

UPGRADE_PACKAGES = environ.get("UPGRADE_PACKAGES", "")
UPGRADE_PACKAGES = UPGRADE_PACKAGES.lower() == "true"

RCLONE_SERVE_URL = environ.get("RCLONE_SERVE_URL", "")
if len(RCLONE_SERVE_URL) == 0:
    RCLONE_SERVE_URL = ""

RCLONE_SERVE_PORT = environ.get("RCLONE_SERVE_PORT", "")
RCLONE_SERVE_PORT = 8080 if len(RCLONE_SERVE_PORT) == 0 else int(RCLONE_SERVE_PORT)

RCLONE_SERVE_USER = environ.get("RCLONE_SERVE_USER", "")
if len(RCLONE_SERVE_USER) == 0:
    RCLONE_SERVE_USER = ""

RCLONE_SERVE_PASS = environ.get("RCLONE_SERVE_PASS", "")
if len(RCLONE_SERVE_PASS) == 0:
    RCLONE_SERVE_PASS = ""

STORAGE_THRESHOLD = environ.get("STORAGE_THRESHOLD", "")
STORAGE_THRESHOLD = "" if len(STORAGE_THRESHOLD) == 0 else float(STORAGE_THRESHOLD)

TORRENT_LIMIT = environ.get("TORRENT_LIMIT", "")
TORRENT_LIMIT = "" if len(TORRENT_LIMIT) == 0 else float(TORRENT_LIMIT)

DIRECT_LIMIT = environ.get("DIRECT_LIMIT", "")
DIRECT_LIMIT = "" if len(DIRECT_LIMIT) == 0 else float(DIRECT_LIMIT)

YTDLP_LIMIT = environ.get("YTDLP_LIMIT", "")
YTDLP_LIMIT = "" if len(YTDLP_LIMIT) == 0 else float(YTDLP_LIMIT)

GDRIVE_LIMIT = environ.get("GDRIVE_LIMIT", "")
GDRIVE_LIMIT = "" if len(GDRIVE_LIMIT) == 0 else float(GDRIVE_LIMIT)

CLONE_LIMIT = environ.get("CLONE_LIMIT", "")
CLONE_LIMIT = "" if len(CLONE_LIMIT) == 0 else float(CLONE_LIMIT)

MEGA_LIMIT = environ.get("MEGA_LIMIT", "")
MEGA_LIMIT = "" if len(MEGA_LIMIT) == 0 else float(MEGA_LIMIT)

LEECH_LIMIT = environ.get("LEECH_LIMIT", "")
LEECH_LIMIT = "" if len(LEECH_LIMIT) == 0 else float(LEECH_LIMIT)

USER_MAX_TASKS = environ.get("USER_MAX_TASKS", "")
USER_MAX_TASKS = int(USER_MAX_TASKS) if USER_MAX_TASKS.isdigit() else ""

USER_TIME_INTERVAL = environ.get("USER_TIME_INTERVAL", "")
USER_TIME_INTERVAL = int(USER_TIME_INTERVAL) if USER_TIME_INTERVAL.isdigit() else 0

PLAYLIST_LIMIT = environ.get("PLAYLIST_LIMIT", "")
PLAYLIST_LIMIT = "" if len(PLAYLIST_LIMIT) == 0 else int(PLAYLIST_LIMIT)

FSUB_IDS = environ.get("FSUB_IDS", "")
if len(FSUB_IDS) == 0:
    FSUB_IDS = ""

BOT_PM = environ.get("BOT_PM", "")
BOT_PM = BOT_PM.lower() == "true"

DAILY_TASK_LIMIT = environ.get("DAILY_TASK_LIMIT", "")
DAILY_TASK_LIMIT = "" if len(DAILY_TASK_LIMIT) == 0 else int(DAILY_TASK_LIMIT)

DAILY_MIRROR_LIMIT = environ.get("DAILY_MIRROR_LIMIT", "")
DAILY_MIRROR_LIMIT = "" if len(DAILY_MIRROR_LIMIT) == 0 else float(DAILY_MIRROR_LIMIT)

DAILY_LEECH_LIMIT = environ.get("DAILY_LEECH_LIMIT", "")
DAILY_LEECH_LIMIT = "" if len(DAILY_LEECH_LIMIT) == 0 else float(DAILY_LEECH_LIMIT)

DISABLE_DRIVE_LINK = environ.get("DISABLE_DRIVE_LINK", "")
DISABLE_DRIVE_LINK = DISABLE_DRIVE_LINK.lower() == "true"

# ── wzv3: Feature disable flags (Heroku load reduction) ──────────────────────
DISABLE_TORRENTS = environ.get("DISABLE_TORRENTS", "")
DISABLE_TORRENTS = DISABLE_TORRENTS.lower() == "true"

DISABLE_LEECH = environ.get("DISABLE_LEECH", "")
DISABLE_LEECH = DISABLE_LEECH.lower() == "true"

DISABLE_BULK = environ.get("DISABLE_BULK", "")
DISABLE_BULK = DISABLE_BULK.lower() == "true"

DISABLE_MULTI = environ.get("DISABLE_MULTI", "")
DISABLE_MULTI = DISABLE_MULTI.lower() == "true"

DISABLE_SEED = environ.get("DISABLE_SEED", "")
DISABLE_SEED = DISABLE_SEED.lower() == "true"

DISABLE_YTDLP = environ.get("DISABLE_YTDLP", "")
DISABLE_YTDLP = DISABLE_YTDLP.lower() == "true"

DISABLE_MIRROR = environ.get("DISABLE_MIRROR", "")
DISABLE_MIRROR = DISABLE_MIRROR.lower() == "true"
# ─────────────────────────────────────────────────────────────────────────────

BOT_THEME = environ.get("BOT_THEME", "")
if len(BOT_THEME) == 0:
    BOT_THEME = "minimal"

IMAGES = environ.get("IMAGES", "")
IMAGES = (
    IMAGES.replace("'", "")
    .replace('"', "")
    .replace("[", "")
    .replace("]", "")
    .replace(",", "")
).split()
if IMAGES:
    STATUS_LIMIT = 2

IMG_SEARCH = environ.get("IMG_SEARCH", "")
IMG_SEARCH = (
    IMG_SEARCH.replace("'", "")
    .replace('"', "")
    .replace("[", "")
    .replace("]", "")
    .replace(",", "")
).split()

IMG_PAGE = environ.get("IMG_PAGE", "")
IMG_PAGE = int(IMG_PAGE) if IMG_PAGE.isdigit() else ""

AUTHOR_NAME = environ.get("AUTHOR_NAME", "")
if len(AUTHOR_NAME) == 0:
    AUTHOR_NAME = "WZML-X"

AUTHOR_URL = environ.get("AUTHOR_URL", "")
if len(AUTHOR_URL) == 0:
    AUTHOR_URL = "https://t.me/WZML_X"

TITLE_NAME = environ.get("TITLE_NAME", "")
if len(TITLE_NAME) == 0:
    TITLE_NAME = "WZ-M/L-X"

COVER_IMAGE = environ.get("COVER_IMAGE", "")
if len(COVER_IMAGE) == 0:
    COVER_IMAGE = "https://graph.org/file/60f9f8bcb97d27f76f5c0.jpg"

GD_INFO = environ.get("GD_INFO", "")
if len(GD_INFO) == 0:
    GD_INFO = "Uploaded by WZML-X"

SAVE_MSG = environ.get("SAVE_MSG", "")
SAVE_MSG = SAVE_MSG.lower() == "true"

SAFE_MODE = environ.get("SAFE_MODE", "")
SAFE_MODE = SAFE_MODE.lower() == "true"

SET_COMMANDS = environ.get("SET_COMMANDS", "true")
SET_COMMANDS = SET_COMMANDS.lower() == "true"

CLEAN_LOG_MSG = environ.get("CLEAN_LOG_MSG", "")
CLEAN_LOG_MSG = CLEAN_LOG_MSG.lower() == "true"

SHOW_EXTRA_CMDS = environ.get("SHOW_EXTRA_CMDS", "")
SHOW_EXTRA_CMDS = SHOW_EXTRA_CMDS.lower() == "true"

TOKEN_TIMEOUT = environ.get("TOKEN_TIMEOUT", "")
TOKEN_TIMEOUT = int(TOKEN_TIMEOUT) if TOKEN_TIMEOUT.isdigit() else ""

LOGIN_PASS = environ.get("LOGIN_PASS", "")
if len(LOGIN_PASS) == 0:
    LOGIN_PASS = None

FILELION_API = environ.get("FILELION_API", "")
if len(FILELION_API) == 0:
    FILELION_API = ""

IMDB_TEMPLATE = environ.get("IMDB_TEMPLATE", "")
if len(IMDB_TEMPLATE) == 0:
    IMDB_TEMPLATE = """<b>Title: </b> {title} [{year}]
<b>Also Known As:</b> {aka}
<b>Rating ⭐️:</b> <i>{rating}</i>
<b>Release Info: </b> <a href="{url_releaseinfo}">{release_date}</a>
<b>Genre: </b>{genres}
<b>IMDb URL:</b> {url}
<b>Language: </b>{languages}
<b>Country of Origin : </b> {countries}

<b>Story Line: </b><code>{plot}</code>

<a href="{url_cast}">Read More ...</a>"""

ANIME_TEMPLATE = environ.get("ANIME_TEMPLATE", "")
if len(ANIME_TEMPLATE) == 0:
    ANIME_TEMPLATE = """<b>{ro_title}</b>({na_title})
<b>Format</b>: <code>{format}</code>
<b>Status</b>: <code>{status}</code>
<b>Start Date</b>: <code>{startdate}</code>
<b>End Date</b>: <code>{enddate}</code>
<b>Season</b>: <code>{season}</code>
<b>Country</b>: {country}
<b>Episodes</b>: <code>{episodes}</code>
<b>Duration</b>: <code>{duration}</code>
<b>Average Score</b>: <code>{avgscore}</code>
<b>Genres</b>: {genres}
<b>Hashtag</b>: {hashtag}
<b>Studios</b>: {studios}

<b>Description</b>: <i>{description}</i>"""

MDL_TEMPLATE = environ.get("MDL_TEMPLATE", "")
if len(MDL_TEMPLATE) == 0:
    MDL_TEMPLATE = """<b>Title:</b> {title}
<b>Also Known As:</b> {aka}
<b>Rating ⭐️:</b> <i>{rating}</i>
<b>Release Info:</b> {aired_date}
<b>Genre:</b> {genres}
<b>MyDramaList URL:</b> {url}
<b>Language:</b> #Korean
<b>Country of Origin:</b> {country}

<b>Story Line:</b> {synopsis}

<a href='{url}'>Read More ...</a>"""

config_dict = {
    "ANIME_TEMPLATE": ANIME_TEMPLATE,
    "AS_DOCUMENT": AS_DOCUMENT,
    "AUTHORIZED_CHATS": AUTHORIZED_CHATS,
    "AUTO_DELETE_MESSAGE_DURATION": AUTO_DELETE_MESSAGE_DURATION,
    "BASE_URL": BASE_URL,
    "BASE_URL_PORT": BASE_URL_PORT,
    "BLACKLIST_USERS": BLACKLIST_USERS,
    "BOT_TOKEN": BOT_TOKEN,
    "BOT_MAX_TASKS": BOT_MAX_TASKS,
    "CAP_FONT": CAP_FONT,
    "CMD_SUFFIX": CMD_SUFFIX,
    "DATABASE_URL": DATABASE_URL,
    "REAL_DEBRID_API": REAL_DEBRID_API,
    "DEBRID_LINK_API": DEBRID_LINK_API,
    "FILELION_API": FILELION_API,
    "DELETE_LINKS": DELETE_LINKS,
    "DEFAULT_UPLOAD": DEFAULT_UPLOAD,
    "DOWNLOAD_DIR": DOWNLOAD_DIR,
    "STORAGE_THRESHOLD": STORAGE_THRESHOLD,
    "TORRENT_LIMIT": TORRENT_LIMIT,
    "DIRECT_LIMIT": DIRECT_LIMIT,
    "YTDLP_LIMIT": YTDLP_LIMIT,
    "GDRIVE_LIMIT": GDRIVE_LIMIT,
    "CLONE_LIMIT": CLONE_LIMIT,
    "MEGA_LIMIT": MEGA_LIMIT,
    "LEECH_LIMIT": LEECH_LIMIT,
    "FSUB_IDS": FSUB_IDS,
    "USER_MAX_TASKS": USER_MAX_TASKS,
    "USER_TIME_INTERVAL": USER_TIME_INTERVAL,
    "PLAYLIST_LIMIT": PLAYLIST_LIMIT,
    "DAILY_TASK_LIMIT": DAILY_TASK_LIMIT,
    "DAILY_MIRROR_LIMIT": DAILY_MIRROR_LIMIT,
    "DAILY_LEECH_LIMIT": DAILY_LEECH_LIMIT,
    "MIRROR_LOG_ID": MIRROR_LOG_ID,
    "LEECH_LOG_ID": LEECH_LOG_ID,
    "LINKS_LOG_ID": LINKS_LOG_ID,
    "EXCEP_CHATS": EXCEP_CHATS,
    "BOT_PM": BOT_PM,
    "DISABLE_DRIVE_LINK": DISABLE_DRIVE_LINK,
    "DISABLE_TORRENTS": DISABLE_TORRENTS,
    "DISABLE_LEECH": DISABLE_LEECH,
    "DISABLE_BULK": DISABLE_BULK,
    "DISABLE_MULTI": DISABLE_MULTI,
    "DISABLE_SEED": DISABLE_SEED,
    "DISABLE_YTDLP": DISABLE_YTDLP,
    "DISABLE_MIRROR": DISABLE_MIRROR,
    "BOT_THEME": BOT_THEME,
    "IMAGES": IMAGES,
    "IMG_SEARCH": IMG_SEARCH,
    "IMG_PAGE": IMG_PAGE,
    "IMDB_TEMPLATE": IMDB_TEMPLATE,
    "AUTHOR_NAME": AUTHOR_NAME,
    "AUTHOR_URL": AUTHOR_URL,
    "COVER_IMAGE": COVER_IMAGE,
    "TITLE_NAME": TITLE_NAME,
    "TIMEZONE": TIMEZONE,
    "GD_INFO": GD_INFO,
    "GDTOT_CRYPT": GDTOT_CRYPT,
    "JIODRIVE_TOKEN": JIODRIVE_TOKEN,
    "EQUAL_SPLITS": EQUAL_SPLITS,
    "EXTENSION_FILTER": EXTENSION_FILTER,
    "GDRIVE_ID": GDRIVE_ID,
    "INCOMPLETE_TASK_NOTIFIER": INCOMPLETE_TASK_NOTIFIER,
    "INDEX_URL": INDEX_URL,
    "IS_TEAM_DRIVE": IS_TEAM_DRIVE,
    "LEECH_FILENAME_PREFIX": LEECH_FILENAME_PREFIX,
    "LEECH_FILENAME_SUFFIX": LEECH_FILENAME_SUFFIX,
    "LEECH_FILENAME_CAPTION": LEECH_FILENAME_CAPTION,
    "LEECH_FILENAME_REMNAME": LEECH_FILENAME_REMNAME,
    "MIRROR_FILENAME_PREFIX": MIRROR_FILENAME_PREFIX,
    "MIRROR_FILENAME_SUFFIX": MIRROR_FILENAME_SUFFIX,
    "MIRROR_FILENAME_REMNAME": MIRROR_FILENAME_REMNAME,
    "LEECH_SPLIT_SIZE": LEECH_SPLIT_SIZE,
    "LOGIN_PASS": LOGIN_PASS,
    "TOKEN_TIMEOUT": TOKEN_TIMEOUT,
    "MDL_TEMPLATE": MDL_TEMPLATE,
    "MEDIA_GROUP": MEDIA_GROUP,
    "MEGA_EMAIL": MEGA_EMAIL,
    "MEGA_PASSWORD": MEGA_PASSWORD,
    "METADATA": METADATA,
    "OWNER_ID": OWNER_ID,
    "QUEUE_ALL": QUEUE_ALL,
    "QUEUE_DOWNLOAD": QUEUE_DOWNLOAD,
    "QUEUE_UPLOAD": QUEUE_UPLOAD,
    "RCLONE_FLAGS": RCLONE_FLAGS,
    "RCLONE_PATH": RCLONE_PATH,
    "RCLONE_SERVE_URL": RCLONE_SERVE_URL,
    "RCLONE_SERVE_USER": RCLONE_SERVE_USER,
    "RCLONE_SERVE_PASS": RCLONE_SERVE_PASS,
    "RCLONE_SERVE_PORT": RCLONE_SERVE_PORT,
    "SAVE_MSG": SAVE_MSG,
    "SAFE_MODE": SAFE_MODE,
    "SET_COMMANDS": SET_COMMANDS,
    "SHOW_MEDIAINFO": SHOW_MEDIAINFO,
    "SCREENSHOTS_MODE": SCREENSHOTS_MODE,
    "CLEAN_LOG_MSG": CLEAN_LOG_MSG,
    "SHOW_EXTRA_CMDS": SHOW_EXTRA_CMDS,
    "SOURCE_LINK": SOURCE_LINK,
    "STATUS_LIMIT": STATUS_LIMIT,
    "STATUS_UPDATE_INTERVAL": STATUS_UPDATE_INTERVAL,
    "STOP_DUPLICATE": STOP_DUPLICATE,
    "SUDO_USERS": SUDO_USERS,
    "TELEGRAM_API": TELEGRAM_API,
    "TELEGRAM_HASH": TELEGRAM_HASH,
    "TORRENT_TIMEOUT": TORRENT_TIMEOUT,
    "UPSTREAM_REPO": UPSTREAM_REPO,
    "UPSTREAM_BRANCH": UPSTREAM_BRANCH,
    "GITHUB_TOKEN": GITHUB_TOKEN,
    "UPGRADE_PACKAGES": UPGRADE_PACKAGES,
    "USER_SESSION_STRING": USER_SESSION_STRING,
    "USER_TD_MODE": USER_TD_MODE,
    "USER_TD_SA": USER_TD_SA,
    "USE_SERVICE_ACCOUNTS": USE_SERVICE_ACCOUNTS,
    "WEB_PINCODE": WEB_PINCODE,
    "YT_DLP_OPTIONS": YT_DLP_OPTIONS,
}

if GDRIVE_ID:
    list_drives_dict["Main"] = {"drive_id": GDRIVE_ID, "index_link": INDEX_URL}
    categories_dict["Root"] = {"drive_id": GDRIVE_ID, "index_link": INDEX_URL}

if ospath.exists("list_drives.txt"):
    with open("list_drives.txt", "r+") as f:
        lines = f.readlines()
        for line in lines:
            sep = 2 if line.strip().split()[-1].startswith("http") else 1
            temp = line.strip().rsplit(maxsplit=sep)
            name = "Main Custom" if temp[0].casefold() == "Main" else temp[0]
            list_drives_dict[name] = {
                "drive_id": temp[1],
                "index_link": (temp[2] if sep == 2 else ""),
            }

if ospath.exists("categories.txt"):
    with open("categories.txt", "r+") as f:
        lines = f.readlines()
        for line in lines:
            sep = 2 if line.strip().split()[-1].startswith("http") else 1
            temp = line.strip().rsplit(maxsplit=sep)
            name = "Root Custom" if temp[0].casefold() == "Root" else temp[0]
            categories_dict[name] = {
                "drive_id": temp[1],
                "index_link": (temp[2] if sep == 2 else ""),
            }

if ospath.exists("buttons.txt"):
    with open("buttons.txt", "r+") as f:
        lines = f.readlines()
        for line in lines:
            temp = line.strip().rsplit(maxsplit=1)
            if len(extra_buttons.keys()) >= 20:
                break
            elif temp[1].startswith("http"):
                extra_buttons[temp[0]] = temp[1]

if ospath.exists("shorteners.txt"):
    with open("shorteners.txt", "r+") as f:
        lines = f.readlines()
        for line in lines:
            temp = line.strip().split()
            if len(temp) == 2:
                shorteners_list.append({"domain": temp[0], "api_key": temp[1]})

# On Heroku, PORT is always set by the platform — start web server even if BASE_URL is
# not configured. Without this, Heroku web dynos get SIGKILL (exit 137) because nothing
# binds to $PORT within the 60-second boot window.
# Also: wserver.py is a Flask (WSGI) app — do NOT use uvicorn.workers.UvicornWorker
# (that is for ASGI/FastAPI). Standard gunicorn sync workers are correct here.
_heroku_port = environ.get("PORT", "")
if BASE_URL or _heroku_port:
    _bind_port = _heroku_port if _heroku_port else str(BASE_URL_PORT)
    Popen(
        f"gunicorn web.wserver:app --bind 0.0.0.0:{_bind_port} --workers 1 --timeout 120",
        shell=True,
    )
    Popen("python3 cron_boot.py", shell=True)

if not ospath.exists(".netrc"):
    with open(".netrc", "w"):
        pass
srun(["chmod", "600", ".netrc"])
srun(["cp", ".netrc", "/root/.netrc"])

# aria2c is always started — it handles direct HTTP downloads too, not just torrents.
# qBittorrent is only started when DISABLE_TORRENTS=False.
srun(["chmod", "+x", "setpkgs.sh"])
srun(f"./setpkgs.sh {BinConfig.ARIA2_NAME}", shell=True)

if not DISABLE_TORRENTS:
    srun([BinConfig.QBIT_NAME, "-d", f"--profile={getcwd()}"], check=False)
    if ospath.exists("accounts.zip"):
        if ospath.exists("accounts"):
            srun(["rm", "-rf", "accounts"])
        srun(["7z", "x", "-o.", "-aoa", "accounts.zip", "accounts/*.json"])
        srun(["chmod", "-R", "777", "accounts"])
        osremove("accounts.zip")
    if not ospath.exists("accounts"):
        config_dict["USE_SERVICE_ACCOUNTS"] = False
else:
    log_info("DISABLE_TORRENTS=True — skipping qBittorrent startup (aria2c still runs for direct downloads)")
    config_dict["USE_SERVICE_ACCOUNTS"] = False

sleep(0.5)

# aria2 and get_client are still defined so existing imports don't break.
# When DISABLE_TORRENTS=True the processes aren't running, so API calls will
# fail gracefully (already wrapped in try/except everywhere they're used).
aria2 = ariaAPI(ariaClient(host="http://localhost", port=6800, secret=""))


def get_client():
    return qbClient(
        host="localhost",
        port=8090,
        VERIFY_WEBUI_CERTIFICATE=False,
        REQUESTS_ARGS={"timeout": (30, 60)},
    )


# aria2c_global is always defined — aria2c always runs (needed for direct downloads)
aria2c_global = [
    "bt-max-open-files",
    "download-result",
    "keep-unfinished-download-result",
    "log",
    "log-level",
    "max-concurrent-downloads",
    "max-download-result",
    "max-overall-download-limit",
    "save-session",
    "max-overall-upload-limit",
    "optimize-concurrent-downloads",
    "save-cookies",
    "server-stat-of",
]

if not DISABLE_TORRENTS:
    def aria2c_init():
        try:
            log_info("Initializing download engine")
            link = "https://linuxmint.com/torrents/lmde-5-cinnamon-64bit.iso.torrent"
            dire = DOWNLOAD_DIR.rstrip("/")
            aria2.add_uris([link], {"dir": dire})
            sleep(3)
            downloads = aria2.get_downloads()
            sleep(10)
            aria2.remove(downloads, force=True, files=True, clean=True)
        except Exception as e:
            log_error(f"Download engine initializing error: {e}")

    Thread(target=aria2c_init).start()

sleep(1.5)

# Load aria2 options — always, since aria2c always runs
try:
    if not aria2_options:
        aria2_options = aria2.client.get_global_option()
    else:
        a2c_glo = {op: aria2_options[op] for op in aria2c_global if op in aria2_options}
        aria2.set_global_options(a2c_glo)
except Exception as _a2_err:
    log_error(f"Aria2c not ready at startup (will retry on first use): {_a2_err}")

# qBittorrent options — only when torrents enabled
if not DISABLE_TORRENTS:
    qb_client = get_client()
    try:
        if not qbit_options:
            qbit_options = dict(qb_client.app_preferences())
            del qbit_options["listen_port"]
            for k in list(qbit_options.keys()):
                if k.startswith("rss"):
                    del qbit_options[k]
        else:
            qb_opt = {**qbit_options}
            for k, v in list(qb_opt.items()):
                if v in ["", "*"]:
                    del qb_opt[k]
            qb_client.app_set_preferences(qb_opt)
    except Exception as _qb_err:
        log_error(f"qBittorrent not ready at startup (will retry on first use): {_qb_err}")

log_info("Creating client from BOT_TOKEN")
bot = wztgClient(
    "bot",
    TELEGRAM_API,
    TELEGRAM_HASH,
    bot_token=BOT_TOKEN,
    workers=min(32, cpu_no + 4),
    parse_mode=enums.ParseMode.HTML,
).start()
# bot_loop is already set at module top (wzv3 style) — do NOT use bot.loop
# bot.loop is deprecated in Python 3.10+ and removed in 3.14
bot_name = bot.me.username
scheduler = AsyncIOScheduler(timezone=str(get_localzone()), event_loop=bot_loop)
