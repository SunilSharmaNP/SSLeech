from logging import (
    FileHandler,
    StreamHandler,
    INFO,
    basicConfig,
    error as log_error,
    info as log_info,
    warning as log_warning,
)
from os import path as ospath, environ, remove
from subprocess import run as srun, call as scall
from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# ── Load bypass patcher into memory BEFORE git reset can delete the file ──
try:
    from bypass_reapply import reapply_bypass as _reapply_bypass
    _bypass_loaded = True
except Exception:
    _bypass_loaded = False

if ospath.exists("log.txt"):
    with open("log.txt", "r+") as f:
        f.truncate(0)

if ospath.exists("rlog.txt"):
    remove("rlog.txt")

basicConfig(
    format="[%(asctime)s] [%(levelname)s] - %(message)s",
    datefmt="%d-%b-%y %I:%M:%S %p",
    handlers=[FileHandler("log.txt"), StreamHandler()],
    level=INFO,
)

# ══════════════════════════════════════════════════════════════════════════════
# WZML-X wzv3 style config loading:
#   Step 1 → read config.env into a plain dict  (file-based defaults)
#   Step 2 → overlay actual os.environ vars     (Heroku config vars WIN)
#   Step 3 → optionally overlay MongoDB vars    (bot-settings panel wins)
# This means: Heroku config vars can never be wiped by a git reset of config.env
# ══════════════════════════════════════════════════════════════════════════════

# Vars used at startup / update time (same list wzv3 uses)
_VAR_LIST = [
    "BOT_TOKEN",
    "TELEGRAM_API",
    "TELEGRAM_HASH",
    "OWNER_ID",
    "DATABASE_URL",
    "BASE_URL",
    "UPSTREAM_REPO",
    "UPSTREAM_BRANCH",
    "UPGRADE_PACKAGES",
]

# Step 1: read config.env (strip whitespace, skip dunder keys)
config_file: dict = {}
if ospath.exists("config.env"):
    config_file = {
        k: (v.strip() if isinstance(v, str) else v)
        for k, v in dotenv_values("config.env").items()
        if not k.startswith("_")
    }

# Step 2: overlay with env vars (Heroku config vars always win)
_env_updates = {
    k: (v.strip() if isinstance(v, str) else v)
    for k, v in environ.items()
    if k in _VAR_LIST
}
if _env_updates:
    log_info("Heroku config vars applied (env vars override config.env for startup keys).")
    config_file.update(_env_updates)

# ── Guard: remove-this-line check ─────────────────────────────────────────────
if config_file.get("_____REMOVE_THIS_LINE_____"):
    log_error("The README.md file there to be read! Exiting now!")
    exit(1)

# ── BOT_TOKEN ─────────────────────────────────────────────────────────────────
BOT_TOKEN = config_file.get("BOT_TOKEN", "")
if not BOT_TOKEN:
    log_error(
        "BOT_TOKEN variable is missing!\n"
        "  Possible causes:\n"
        "  1. BOT_TOKEN not set in Heroku config vars OR config.env\n"
        "  2. config.env has empty BOT_TOKEN after git reset (set as Heroku config var)\n"
        "Exiting now."
    )
    exit(1)

bot_id = BOT_TOKEN.split(":", 1)[0]

# ── MongoDB: step 3 — overlay bot-settings panel values ───────────────────────
DATABASE_URL = config_file.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    try:
        conn = MongoClient(DATABASE_URL, server_api=ServerApi("1"), serverSelectionTimeoutMS=10000)
        db = conn.wzmlx

        # wzv3 pattern: compare deploy snapshot to decide whether to pull from DB
        old_config = db.settings.deployConfig.find_one({"_id": bot_id}, {"_id": 0})
        db_config = db.settings.config.find_one({"_id": bot_id})

        if (old_config is None or old_config == config_file) and db_config is not None:
            # Pull UPSTREAM_REPO / UPSTREAM_BRANCH from bot-settings if user changed them
            if db_config.get("UPSTREAM_REPO"):
                config_file["UPSTREAM_REPO"] = db_config["UPSTREAM_REPO"]
            if db_config.get("UPSTREAM_BRANCH"):
                config_file["UPSTREAM_BRANCH"] = db_config["UPSTREAM_BRANCH"]
            if db_config.get("UPGRADE_PACKAGES") is not None:
                config_file["UPGRADE_PACKAGES"] = str(db_config["UPGRADE_PACKAGES"])
        conn.close()
        log_info("MongoDB: startup config loaded.")
    except Exception as db_err:
        log_warning(f"MongoDB not available during update (bot will still start): {db_err}")

# ── Update packages ────────────────────────────────────────────────────────────
UPGRADE_PACKAGES = config_file.get("UPGRADE_PACKAGES", "False")
if (isinstance(UPGRADE_PACKAGES, str) and UPGRADE_PACKAGES.lower() == "true") or UPGRADE_PACKAGES is True:
    log_info("Upgrading installed packages ...")
    scall("uv pip install --system -U -r requirements.txt --quiet", shell=True)
    log_info("Packages updated successfully.")

# ── Upstream repo update ────────────────────────────────────────────────────────
UPSTREAM_REPO = config_file.get("UPSTREAM_REPO", "").strip()
UPSTREAM_BRANCH = config_file.get("UPSTREAM_BRANCH", "").strip() or "master"

if UPSTREAM_REPO:
    # ── Backup config.env BEFORE git reset overwrites it ──────────────────────
    _config_env_backup = None
    if ospath.exists("config.env"):
        try:
            with open("config.env", "r", encoding="utf-8") as _cf:
                _config_env_backup = _cf.read()
            log_info("config.env backed up before upstream reset.")
        except Exception as e:
            log_warning(f"Could not backup config.env: {e}")

    # ── Safe display URL (strip token from logs if embedded) ──────────────────
    # Private repo: embed token directly in UPSTREAM_REPO
    #   e.g. https://TOKEN@github.com/user/repo
    # Public repo: plain https://github.com/user/repo
    _fetch_url = UPSTREAM_REPO
    if "@github.com" in _fetch_url:
        # Token is embedded — build a clean URL for display (don't log the token)
        _parts = _fetch_url.split("@github.com/", 1)
        _display = f"https://github.com/{_parts[1]}" if len(_parts) == 2 else _fetch_url
    else:
        _display = _fetch_url

    if ospath.exists(".git"):
        srun(["rm", "-rf", ".git"])

    # GIT_TERMINAL_PROMPT=0  → git never tries to open /dev/tty for credentials
    # GIT_ASKPASS=echo       → if git asks for password, return empty string (silent fail)
    # These fix "fatal: could not read Username ... No such device or address" on Heroku/Docker
    _git_env = {
        **environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "echo",
    }

    update = srun(
        f'git init -q'
        f' && git config --global user.email bot@ssleech.com'
        f' && git config --global user.name ssleech-bot'
        f' && git add .'
        f' && git commit -sm update -q'
        f' && git remote add origin {_fetch_url}'
        f' && git fetch origin -q'
        f' && git reset --hard origin/{UPSTREAM_BRANCH} -q',
        shell=True,
        env=_git_env,
    )

    # ── Restore config.env AFTER git reset (prevents credential wipe) ─────────
    if _config_env_backup is not None:
        try:
            with open("config.env", "w", encoding="utf-8") as _cf:
                _cf.write(_config_env_backup)
            log_info("config.env restored after upstream reset.")
        except Exception as e:
            log_error(f"Could not restore config.env: {e}")

    if update.returncode == 0:
        log_info(f"Upstream updated successfully! Repo: {_display} | Branch: {UPSTREAM_BRANCH}")
        # Re-apply Heroku bypass patches after git reset
        if _bypass_loaded:
            try:
                _reapply_bypass()
                log_info("Heroku bypass patches re-applied.")
            except Exception as e:
                log_error(f"Bypass re-apply failed: {e}")
        else:
            log_warning("bypass_reapply module not loaded — bypass patches may be missing after reset.")
    else:
        log_error(
            f"Upstream update FAILED (repo: {_display}, branch: {UPSTREAM_BRANCH}).\n"
            "  Possible causes:\n"
            "  1. Private repo — embed token in UPSTREAM_REPO: https://TOKEN@github.com/user/repo\n"
            "  2. UPSTREAM_BRANCH does not exist on the remote\n"
            "  3. Invalid UPSTREAM_REPO URL\n"
            "Bot will continue with current (pre-reset) code."
        )
