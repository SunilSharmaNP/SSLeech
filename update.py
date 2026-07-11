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


def _fetch_upstream_from_db(database_url, bot_id):
    """
    Connect to MongoDB (synchronous pymongo) and return
    (UPSTREAM_REPO, UPSTREAM_BRANCH) stored via botsettings.
    Returns ("", "") on any error.
    """
    try:
        from pymongo import MongoClient

        conn = MongoClient(database_url, serverSelectionTimeoutMS=8000)
        doc = conn.wzmlx.settings.config.find_one({"_id": bot_id})
        conn.close()
        if doc:
            repo = str(doc.get("UPSTREAM_REPO") or "").strip()
            branch = str(doc.get("UPSTREAM_BRANCH") or "").strip()
            return repo, branch
    except Exception as e:
        _LOGGER.warning(f"MongoDB: could not fetch upstream config — {e}")
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
    _LOGGER.info("Checking packages against requirements.txt ...")
    # --upgrade-strategy only-if-needed  →  pip skips packages already satisfying
    # the pinned constraint; no unnecessary upgrades of base-image packages.
    # -U / --upgrade is intentionally OMITTED so that on each restart only truly
    # new or version-changed deps are installed, keeping restarts fast.
    ret = scall(
        "pip install -r requirements.txt -q --no-warn-script-location "
        "--upgrade-strategy only-if-needed",
        shell=True,
    )
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

    if database_url and (not upstream_repo or not upstream_branch):
        db_repo, db_branch = _fetch_upstream_from_db(database_url, bot_id)
        if db_repo and not upstream_repo:
            upstream_repo = db_repo
            _LOGGER.info("MongoDB: UPSTREAM_REPO loaded from botsettings.")
        if db_branch and not upstream_branch:
            upstream_branch = db_branch
        _LOGGER.info("MongoDB: startup config loaded.")

    upstream_branch = upstream_branch or "merge"

    # ── Step 3: Pull upstream code FIRST (gets updated requirements.txt) ─────
    _run_update(upstream_repo, upstream_branch)

    # ── Step 4: Install packages from the freshly pulled requirements.txt ────
    _update_packages()


if __name__ == "__main__":
    main()
