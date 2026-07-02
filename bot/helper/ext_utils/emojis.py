#!/usr/bin/env python3
"""
Premium Custom Emoji helper for hardcoded bot messages (outside themes).

HOW IT WORKS
────────────
By default, E.xxx returns the plain Unicode fallback emoji so the bot never
triggers a DOCUMENT_INVALID error.

Custom <emoji> HTML tags are ONLY emitted when BOTH conditions are true:
  1. USE_CUSTOM_EMOJI = True  (set in config.env OR toggled via Bot Settings)
  2. The per-call plain=False (default)

To enable animated emojis for the bot account:
    from bot.helper.ext_utils.emojis import E
    E.enable()          # call once after confirming bot can send custom emojis
    E.disable()         # revert to plain fallback at any time

Usage:
    from bot.helper.ext_utils.emojis import E
    await sendMessage(msg, f"{E.fire} Upload Complete!")
    btns.ibutton(f"{E.get('download', plain=True)} Download", cb)
"""

import os


class _Emoji:
    _MAP = {
        # ── User-provided verified IDs ──────────────────────────────────────
        "comet":     ("5224607267797606837", "☄️"),
        "trending":  ("5244837092042750681", "📈"),
        "phone":     ("5359772714691216710", "📱"),
        "bolt":      ("5456140674028019486", "⚡️"),
        "gear":      ("5341715473882955310", "⚙️"),

        # ── From custom_emojis.py (verified real IDs) ───────────────────────
        "magnet":    ("5377535110289576661", "🧲"),
        "sparkle":   ("5325547803936572038", "✨"),
        "party":     ("5235711785482341993", "🎉"),
        "announce":  ("5424818078833715060", "📣"),
        "up_tri":    ("5971972727383264364", "🔺"),
        "diamond":   ("5328089410963513796", "💠"),
        "link":      ("5271604874419647061", "🔗"),
        "download":  ("5443127283898405358", "📥"),
        "upload":    ("5445355530111437729", "📤"),
        "gem":       ("6244241334320762892", "💎"),
        "computer":  ("5976578040426139845", "💻"),
        "star":      ("5267500801240092311", "⭐"),
        "explosion": ("6298644001432012664", "💥"),
        "drop":      ("5393512611968995988", "💧"),
        "fire":      ("5220166546491459639", "🔥"),
        "dizzy":     ("5469744063815102906", "💫"),
        "eye":       ("5032776298733240935", "👁"),
        "coin":      ("5202064723922670546", "🪙"),
        "takeoff":   ("5201691993775818138", "🛫"),
        "chart":     ("5429518319243775957", "📉"),
        "timer":     ("5382194935057372936", "⏱"),
        "bag":       ("5294167145079395967", "🛍"),

        # ── Status & result ─────────────────────────────────────────────────
        "done":      ("5368324170671202286", "✅"),
        "error":     ("5447644880824181073", "❌"),
        "warning":   ("5467406605516091496", "⚠️"),
        "cancel":    ("5240241223632954241", "🚫"),
        "stop":      ("5467406605516091496", "🛑"),
        "mirror":    ("5471952986970267163", "🔄"),
        "restart":   ("5471952986970267163", "🔄"),

        # ── Task & progress ─────────────────────────────────────────────────
        "rocket":    ("5433655514094022326", "🚀"),
        "speed":     ("5445284980978621387", "⚡"),
        "clock":     ("5301085541559983872", "⏳"),
        "zip":       ("5379763379953803263", "📦"),
        "folder":    ("6026239398650056451", "📁"),
        "openfolder":("5379763379953803263", "📂"),

        # ── Media & files ────────────────────────────────────────────────────
        "video":     ("5373123633415074227", "🎥"),
        "image":     ("5373123633415074227", "🖼"),
        "note":      ("5373123633415074227", "📝"),
        "info":      ("5373123633415074227", "ℹ️"),
        "file":      ("5373123633415074227", "📄"),
        "log":       ("5373123633415074227", "📑"),

        # ── System stats ─────────────────────────────────────────────────────
        "cpu":       ("5976578040426139845", "🖥️"),
        "ram":       ("5471952986970267163", "🧠"),
        "disk":      ("5471952986970267163", "💿"),
        "green":     ("5368324170671202286", "🟢"),

        # ── User & identity ──────────────────────────────────────────────────
        "user":      ("5373123633415074227", "👤"),
        "robot":     ("5431815506048155538", "🤖"),
        "crown":     ("5471952986970267163", "👑"),
        "shield":    ("5445284980978621387", "🛡"),

        # ── Links & navigation ───────────────────────────────────────────────
        "cloud":     ("5471952986970267163", "☁️"),
        "recycle":   ("5471952986970267163", "♻️"),
        "lock":      ("5291873529464122510", "🔐"),
        "unlock":    ("5291873529464122510", "🔓"),
        "globe":     ("5471952986970267163", "🌐"),
        "search":    ("5471952986970267163", "🔍"),

        # ── Misc ─────────────────────────────────────────────────────────────
        "megaphone": ("5424818078833715060", "📢"),
        "mail":      ("5424818078833715060", "📨"),
        "inbox":     ("5443127283898405358", "📩"),
        "pray":      ("5325547803936572038", "🙏"),
        "heart":     ("5471952986970267163", "❤️"),
        "wand":      ("5325547803936572038", "🪄"),
    }

    # Read env var at import time. Runtime toggle via E.enable()/E.disable()
    # or via config_dict["USE_CUSTOM_EMOJI"] (checked by message_utils).
    _use_custom: bool = os.environ.get("USE_CUSTOM_EMOJI", "").lower() == "true"

    def enable(self) -> None:
        object.__setattr__(self, "_use_custom", True)

    def disable(self) -> None:
        object.__setattr__(self, "_use_custom", False)

    def _render(self, eid: str, fallback: str) -> str:
        if self._use_custom:
            return f'<emoji id="{eid}">{fallback}</emoji>'
        return fallback

    def __getattr__(self, name: str) -> str:
        if name.startswith("_"):
            raise AttributeError(name)
        entry = self._MAP.get(name)
        if entry is None:
            return name
        eid, fallback = entry
        return self._render(eid, fallback)

    def get(self, name: str, plain: bool = False) -> str:
        """
        Return emoji for use in a message or button label.

        plain=True  → always return the Unicode fallback (safe for button text)
        plain=False → return <emoji> tag if custom emojis are enabled, else fallback
        """
        entry = self._MAP.get(name)
        if entry is None:
            return name
        eid, fallback = entry
        return fallback if plain else self._render(eid, fallback)


E = _Emoji()
