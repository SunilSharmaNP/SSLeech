"""
Loaded into memory BEFORE git reset so it persists even after git reset
deletes/overwrites this file.  Called by update.py after the reset to
re-apply patches that git reset would otherwise undo.
"""
from logging import getLogger
from os import path as ospath

log = getLogger(__name__)


def reapply_bypass():
    """Re-apply all Heroku-compatibility patches after git reset --hard."""
    _patch_update_py()


# ── update.py ────────────────────────────────────────────────────────────────

_UPDATE_OLD = (
    'packages = [dist.metadata["Name"] for dist in distributions()]\n'
    '    scall("uv pip install --system " + " ".join(packages), shell=True)'
)

_UPDATE_NEW = (
    '# --no-build : only pre-built wheels, no source compilation (lxml needs libxml2-dev)\n'
    '    # --no-deps  : skip transitive-dep resolution so lxml is not pulled in indirectly\n'
    '    _SKIP_BUILD = {"lxml", "cryptography", "uwsgi", "grpcio"}\n'
    '    packages = [\n'
    '        dist.metadata["Name"]\n'
    '        for dist in distributions()\n'
    '        if dist.metadata["Name"].lower() not in _SKIP_BUILD\n'
    '    ]\n'
    '    scall(\n'
    '        "uv pip install --system --no-build --no-deps " + " ".join(packages),\n'
    '        shell=True,\n'
    '    )'
)


def _patch_update_py():
    path = "update.py"
    if not ospath.exists(path):
        log.warning("bypass_reapply: update.py not found, skipping patch")
        return

    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()

    if _UPDATE_OLD in content:
        content = content.replace(_UPDATE_OLD, _UPDATE_NEW)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        log.info("bypass_reapply: update.py patched (uv --no-build --no-deps)")
    elif _UPDATE_NEW in content:
        log.info("bypass_reapply: update.py already patched, skipping")
    else:
        log.warning("bypass_reapply: update.py pattern not found — upstream may have changed")
      
