"""
bypass_reapply.py — Critical patch file.

HOW IT WORKS:
  1. update.py imports this module into Python MEMORY before git reset happens.
  2. git reset --hard wipes this file from disk (along with all other fixes).
  3. update.py calls reapply_bypass() from memory AFTER git reset.
  4. reapply_bypass() patches the freshly-reset upstream files AND writes
     itself back to disk AND injects a self-call into update.py.
  5. On every subsequent restart the injected update.py calls us again
     — so patches persist forever, even when SSLeech's update.py runs.

PATCHES APPLIED:
  A) bot/__init__.py  — Any "elif" in the MongoDB config loading block is
     changed to "if" so bot settings always apply on restart regardless of
     the deployConfig snapshot comparison. Uses regex to handle any variable
     name or whitespace variant in SSLeech's code.
  B) bot/helper/ext_utils/db_handler.py — db_load() must NOT overwrite the
     user's MongoDB settings on every startup. Changed to only write when no
     document exists yet (first-time setup). Prevents permanent erasure of
     /botsettings changes.
  C) update.py — injects a self-perpetuating call at the end so this bypass
     survives future git resets automatically.
"""

import os as _os
import re as _re
import logging as _log

# Read own source into memory at import-time (before git reset wipes the file).
_SELF_SOURCE = ""
try:
    _self_path = _os.path.abspath(__file__)
    if _os.path.exists(_self_path):
        with open(_self_path, "r", encoding="utf-8") as _sf:
            _SELF_SOURCE = _sf.read()
except Exception:
    pass

# Code snippet appended to update.py so the bypass call survives future resets.
_UPDATE_PY_INJECTION = '''

# ── bypass_reapply: self-perpetuating patch hook (do not remove) ──────────────
try:
    from bypass_reapply import reapply_bypass as _bypass_fn
    _bypass_fn()
    import logging as _bl; _bl.getLogger(__name__).info("Bypass patches applied.")
except Exception as _be:
    import logging as _bl; _bl.getLogger(__name__).warning(f"Bypass patch skipped: {_be}")
# ── end bypass_reapply ─────────────────────────────────────────────────────────
'''


def reapply_bypass():
    """
    Entry point called by update.py after git reset.
    Applies all patches and makes the bypass self-perpetuating.
    """
    _write_self_back()
    _patch_update_py()
    _patch_bot_init()
    _patch_db_handler()


# ── Individual patch functions ─────────────────────────────────────────────────

def _write_self_back():
    """Recreate bypass_reapply.py on disk (git reset deleted it)."""
    if not _SELF_SOURCE:
        _log.warning("bypass_reapply: self-source empty, cannot write back.")
        return
    try:
        with open("bypass_reapply.py", "w", encoding="utf-8") as f:
            f.write(_SELF_SOURCE)
    except Exception as e:
        _log.warning(f"bypass_reapply: could not write self back: {e}")


def _patch_update_py():
    """
    Append bypass call to update.py so it persists across future git resets.
    Idempotent: only adds the injection if it isn't already there.
    """
    path = "update.py"
    if not _os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if "bypass_reapply: self-perpetuating patch hook" in content:
            return  # already injected
        content += _UPDATE_PY_INJECTION
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        _log.warning(f"bypass_reapply: could not patch update.py: {e}")


def _patch_bot_init():
    """
    Fix bot/__init__.py MongoDB settings loading.

    WZML-X / SSLeech original pattern uses `elif` which means bot settings
    from the /botsettings panel are ONLY loaded when the deployConfig snapshot
    matches config.env exactly. After a git reset the snapshot often differs,
    so the `elif` branch is never reached and all settings revert to defaults.

    Fix: change `elif` to `if` so settings are loaded unconditionally.

    Uses regex so it handles any variable name or whitespace variant that
    SSLeech uses (e.g. config_dict, db_bot_config, bot_config, etc.).
    """
    path = "bot/__init__.py"
    if not _os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Regex: match `elif <var> := db.settings.config.find_one(` with any
        # variable name and any whitespace around the walrus operator.
        pattern = _re.compile(
            r'\belif\b(\s+\w+\s*:=\s*db\.settings\.config\.find_one\s*\()',
            _re.MULTILINE,
        )
        new_content, n = pattern.subn(r'if\1', content)

        # Fallback: older WZML-X without walrus — elif on a separate line
        # e.g.:  elif config_dict:
        if n == 0:
            pattern2 = _re.compile(
                r'\belif\b(\s+\w+\s*:(?!=))\s*\n(\s+.*find_one.*settings\.config)',
                _re.MULTILINE,
            )
            new_content, n = pattern2.subn(r'if\1\n\2', content)

        if n > 0:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            _log.info(f"bypass_reapply: bot/__init__.py patched ({n} elif→if).")
        else:
            _log.info(
                "bypass_reapply: bot/__init__.py — no elif pattern found "
                "(already patched or SSLeech uses a different structure)."
            )
    except Exception as e:
        _log.warning(f"bypass_reapply: could not patch bot/__init__.py: {e}")


def _patch_db_handler():
    """
    Fix bot/helper/ext_utils/db_handler.py — db_load() config overwrite bug.

    Original db_load() does:
        await db.settings.config.update_one({"_id": bot_id},
                                             {"$set": config_dict}, upsert=True)
    on EVERY startup. If bot settings were not loaded from MongoDB yet (because
    the elif condition in bot/__init__.py was not met), config_dict contains
    only default/Heroku values and this $set PERMANENTLY ERASES the user's
    /botsettings changes from MongoDB.

    Fix: only write config to MongoDB when no document exists yet (first-time
    setup). Subsequent restarts must never overwrite.
    """
    path = "bot/helper/ext_utils/db_handler.py"
    if not _os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Already patched?
        if "existing_config" in content or "first-ever startup" in content:
            _log.info("bypass_reapply: db_handler.py already patched.")
            return

        # Pattern to replace — the unconditional $set of config_dict
        old = (
            '        # Save bot settings\n'
            '        await self.__db.settings.config.update_one(\n'
            '            {"_id": bot_id}, {"$set": config_dict}, upsert=True\n'
            '        )'
        )
        new = (
            '        # Save bot settings ONLY on first-ever startup.\n'
            '        # Never overwrite on subsequent restarts — that would erase\n'
            '        # settings the user changed via /botsettings.\n'
            '        existing_config = await self.__db.settings.config.find_one({"_id": bot_id})\n'
            '        if existing_config is None:\n'
            '            await self.__db.settings.config.update_one(\n'
            '                {"_id": bot_id}, {"$set": config_dict}, upsert=True\n'
            '            )'
        )
        if old in content:
            content = content.replace(old, new)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            _log.info("bypass_reapply: db_handler.py patched (db_load overwrite fix).")
        else:
            # Try a regex-based fallback for slight whitespace variations
            pattern = _re.compile(
                r'(#\s*Save bot settings\s*\n\s*)'
                r'(await self\.__db\.settings\.config\.update_one\s*\(\s*\n'
                r'\s*\{"_id":\s*bot_id\}\s*,\s*\{"\$set":\s*config_dict\}\s*,\s*upsert=True\s*\n'
                r'\s*\))',
                _re.MULTILINE,
            )
            replacement = (
                '# Save bot settings ONLY on first-ever startup.\n'
                '        # Never overwrite on subsequent restarts — that would erase\n'
                '        # settings the user changed via /botsettings.\n'
                '        existing_config = await self.__db.settings.config.find_one({"_id": bot_id})\n'
                '        if existing_config is None:\n'
                '            await self.__db.settings.config.update_one(\n'
                '                {"_id": bot_id}, {"$set": config_dict}, upsert=True\n'
                '            )'
            )
            new_content, n = pattern.subn(replacement, content)
            if n > 0:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                _log.info("bypass_reapply: db_handler.py patched via regex fallback.")
            else:
                _log.warning(
                    "bypass_reapply: db_handler.py — pattern not found. "
                    "SSLeech may have changed db_load() structure."
                )
    except Exception as e:
        _log.warning(f"bypass_reapply: could not patch db_handler.py: {e}")
