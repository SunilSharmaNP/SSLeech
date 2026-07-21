#!/usr/bin/env python3
"""
update.py — wzv3-style clean update for SSLeech on Heroku.

MINIMUM required Heroku config vars (only these 2 are mandatory):
  BOT_TOKEN     — identifies which MongoDB partition to load
  DATABASE_URL  — MongoDB connection string

Everything else (UPSTREAM_REPO, UPSTREAM_BRANCH, TELEGRAM_API, TELEGRAM_HASH,
OWNER_ID, etc.) is loaded from MongoDB automatically via bot/__init__.py.
You only need them in Heroku config vars for the VERY FIRST boot.
After that they persist in MongoDB and can be removed from Heroku.

Design (same as wzv3 branch):
  1. Read BOT_TOKEN + DATABASE_URL from Heroku env
  2. Fetch UPSTREAM_REPO / UPSTREAM_BRANCH from MongoDB (so botsettings value works)
  3. Clean `git reset --hard origin/<branch>`  — no file backup/restore
  4. pip install requirements
  NO bypass_reapply.py needed — GitHub code is always the authoritative source.
"""

from logging import ERROR, INFO, FileHandler, StreamHandler, basicConfig, getLogger
from os import environ, path, remove
from subprocess import call as scall
from subprocess import run as srun
from sys import exit

getLogger("pymongo").setLevel(ERROR)
_LOGGER = getLogger("update")


def _setup_logging():
    for f in ("log.txt", "rlog.txt"):
        if path.exists(f):
            with open(f, "w"):
                pass
    basicConfig(
        format="[%(asctime)s] [%(levelname)s] - %(message)s",
        datefmt="%d-%b-%y %I:%M:%S %p",
        handlers=[FileHandler("log.txt"), StreamHandler()],
        level=INFO,
    )


def _get_essential(key):
    """Read a mandatory var from Heroku env; also check config.env as fallback."""
    val = environ.get(key, "").strip()
    if val:
        return val
    # Fallback: try reading config.env directly (may exist from previous run)
    if path.exists("config.env"):
        for line in open("config.env"):
            line = line.strip()
            if line.startswith(f"{key}="):
                return line[len(key) + 1 :].strip().strip('"').strip("'")
    return ""


def _fetch_config_from_db(database_url, bot_id):
    """
    Connect to MongoDB and:
      1. Inject ALL saved config vars into os.environ (Heroku vars take priority).
      2. Return (UPSTREAM_REPO, UPSTREAM_BRANCH).

    Doing this here means bot/__init__.py can find TELEGRAM_API, TELEGRAM_HASH,
    OWNER_ID etc. in os.environ even if its own MongoDB call fails or the
    deployConfig-change guard skips the load.
    """
    try:
        from pymongo import MongoClient

        conn = MongoClient(database_url, serverSelectionTimeoutMS=8000)
        doc = conn.wzmlx.settings.config.find_one({"_id": bot_id})
        conn.close()
        if doc:
            loaded = 0
            for key, value in doc.items():
                if key == "_id" or value is None:
                    continue
                # Heroku config vars already in environ take priority
                if not environ.get(key):
                    environ[key] = str(value)
                    loaded += 1
            _LOGGER.info(f"MongoDB: {loaded} config var(s) pre-loaded into environment.")
            repo   = str(doc.get("UPSTREAM_REPO")   or "").strip()
            branch = str(doc.get("UPSTREAM_BRANCH") or "").strip()
            return repo, branch
    except Exception as e:
        _LOGGER.warning(f"MongoDB: could not load config — {e}")
    return "", ""


def _run_update(upstream_repo, upstream_branch):
    """
    wzv3-style clean git reset — no backup, no restore, no bypass file.
    GitHub repo is always the authoritative source for code.
    """
    if not upstream_repo:
        _LOGGER.info("No UPSTREAM_REPO set — skipping git update.")
        return

    # ── Preserve runtime files that must survive git reset ────────────────────
    # .restartmsg holds (chat_id, msg_id) written by _do_restart() so the bot
    # can edit "Restarting…" → "Restarted Successfully!" after coming back up.
    # git add . stages it, then git reset --hard deletes it — we save/restore it.
    _RUNTIME_FILES = [".restartmsg"]
    _saved = {}
    for _f in _RUNTIME_FILES:
        if path.exists(_f):
            with open(_f, "r") as _fh:
                _saved[_f] = _fh.read()

    if path.exists(".git"):
        srun(["rm", "-rf", ".git"], capture_output=True)

    cmds = [
        ["git", "init", "-q"],
        # Auto-configure git identity so `git commit` in botsettings push works
        ["git", "config", "--global", "user.email", "bot@heroku.local"],
        ["git", "config", "--global", "user.name", "SSLeechBot"],
        ["git", "add", "."],
        ["git", "commit", "-sm", "pre-update", "-q"],
        ["git", "remote", "add", "origin", upstream_repo],
        ["git", "fetch", "origin", upstream_branch, "-q"],
        ["git", "reset", "--hard", f"origin/{upstream_branch}", "-q"],
    ]

    result = None
    for cmd in cmds:
        result = srun(cmd, capture_output=True)
        if result.returncode != 0:
            _LOGGER.error(
                f"git command failed: {' '.join(cmd)}\n"
                f"stderr: {result.stderr.decode().strip()}"
            )
            break

    # ── Restore preserved runtime files ───────────────────────────────────────
    for _f, _content in _saved.items():
        with open(_f, "w") as _fh:
            _fh.write(_content)

    if result and result.returncode == 0:
        _LOGGER.info("Successfully updated with latest commits !!")
        display = "/".join(upstream_repo.split("/")[-2:]).replace(".git", "")
        _LOGGER.info(
            f"UPSTREAM_REPO: {display} | UPSTREAM_BRANCH: {upstream_branch}"
        )
    else:
        _LOGGER.error(
            "Update failed! Check UPSTREAM_REPO/UPSTREAM_BRANCH in botsettings "
            "or Heroku config vars."
        )


def _update_packages():
    """
    Install / upgrade packages from requirements.txt.

    Priority:
      1. uv  — fast Rust-based installer, present in newer base images.
               Must use --system so it doesn't demand a venv.
      2. /wzvenv/bin/pip  — virtualenv bundled in some base images.
      3. System pip (pip3 / pip) via shutil.which — PEP-668 safe with
               --break-system-packages on Python 3.12+.
    """
    from shutil import which

    _LOGGER.info("Checking packages against requirements.txt ...")

    # ── 1. Try uv first (handles the 'No virtual environment found' error by
    #        adding --system, which installs into the system Python) ──────────
    uv_bin = which("uv")
    if uv_bin:
        pip_cmd = f"{uv_bin} pip install --system -r requirements.txt -q"
        _LOGGER.info(f"Package installer: uv ({uv_bin})")
    else:
        # ── 2. Absolute-path venv pip (base image) ───────────────────────────
        _pip_candidates = ["/wzvenv/bin/pip", "/usr/local/bin/pip"]
        _pip_bin = next((p for p in _pip_candidates if path.exists(p)), None)
        # ── 3. System pip via PATH ─────────────────────────────────────────────
        if not _pip_bin:
            _pip_bin = which("pip3") or which("pip") or "pip3"
        pip_cmd = (
            f"{_pip_bin} install -r requirements.txt -q "
            "--no-warn-script-location "
            "--upgrade-strategy only-if-needed "
            "--break-system-packages"
        )
        _LOGGER.info(f"Package installer: pip ({_pip_bin})")

    ret = scall(pip_cmd, shell=True)
    if ret == 0:
        _LOGGER.info("Successfully Updated all the Packages !")
    else:
        _LOGGER.warning("Package install had warnings — continuing anyway.")


def main():
    _setup_logging()

    # ── Step 1: Read mandatory Heroku config vars ─────────────────────────────
    bot_token = _get_essential("BOT_TOKEN")
    if not bot_token:
        _LOGGER.error(
            "BOT_TOKEN is missing!\n"
            "  BOT_TOKEN must be set in Heroku config vars (Settings → Config Vars).\n"
            "  It cannot be removed — it is needed to identify which bot to run."
        )
        exit(1)
    _LOGGER.info("Heroku config vars applied (env vars override config.env for startup keys).")

    database_url = _get_essential("DATABASE_URL")
    bot_id = bot_token.split(":", 1)[0]

    # ── Step 2: Load UPSTREAM_REPO / BRANCH from MongoDB (botsettings) ───────
    # This is the wzv3 key insight: config set via /botsettings is honoured
    # here too, so you can manage UPSTREAM_REPO entirely from Telegram.
    upstream_repo = _get_essential("UPSTREAM_REPO")
    upstream_branch = _get_essential("UPSTREAM_BRANCH")

    if database_url:
        db_repo, db_branch = _fetch_config_from_db(database_url, bot_id)
        if db_repo and not upstream_repo:
            upstream_repo = db_repo
            _LOGGER.info("MongoDB: UPSTREAM_REPO loaded from database.")
        if db_branch and not upstream_branch:
            upstream_branch = db_branch

    upstream_branch = upstream_branch or "merge"

    # ── Step 3: Pull upstream code FIRST (gets updated requirements.txt) ─────
    _run_update(upstream_repo, upstream_branch)

    # ── Step 4: Install packages from the freshly pulled requirements.txt ────
    _update_packages()


if __name__ == "__main__":
    main()
