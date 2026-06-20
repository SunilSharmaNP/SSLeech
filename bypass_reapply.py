"""
bypass_reapply.py

Kept for backward compatibility in case old injection in SSLeech's update.py
calls reapply_bypass(). The real fixes now live in:
  - bot/__init__.py       (restored directly by update.py after git reset)
  - bot/helper/ext_utils/db_handler.py  (same)

No patching or self-writing is needed here anymore.
"""


def reapply_bypass():
    import logging
    logging.getLogger(__name__).info(
        "bypass_reapply: called (no-op — fixes are restored directly by update.py)."
    )
