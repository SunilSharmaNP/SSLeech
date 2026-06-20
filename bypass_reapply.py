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
  A) bot/__init__.py  — "elif" → "if" for MongoDB config loading so bot
     settings always apply on restart regardless of deployConfig snapshot.
  B) update.py        — injects a self-perpetuating call at the end so
     this bypass survives future git resets automatically.
"""

import os as _os
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
    Append our self-call to update.py so it persists across future git resets.
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
    matches config.env exactly.  After a git reset the snapshot often differs
    (different config.env template in the upstream repo), so the `elif` branch
    is never reached and all settings revert to defaults on every restart.

    Fix: change `elif` to `if` so settings are loaded unconditionally.
    """
    path = "bot/__init__.py"
    if not _os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        changed = False

        # Pattern used by WZML-X and SSLeech:
        #   elif config_dict := db.settings.config.find_one({"_id": bot_id}):
        for old, new in [
            (
                'elif config_dict := db.settings.config.find_one({"_id": bot_id}):',
                'if config_dict := db.settings.config.find_one({"_id": bot_id}):',
            ),
            # Variant without walrus operator (older versions):
            (
                'elif config_dict:\n',
                'if config_dict:\n',
            ),
        ]:
            if old in content:
                content = content.replace(old, new)
                changed = True

        if changed:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            _log.info("bypass_reapply: bot/__init__.py already patched or pattern not found.")
    except Exception as e:
        _log.warning(f"bypass_reapply: could not patch bot/__init__.py: {e}")
