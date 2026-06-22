#!/usr/bin/env python3
"""
Premium Custom Emoji helper for hardcoded bot messages (outside themes).

IDs sourced from bot/helper/themes/custom_emojis.py (your verified IDs).
Use E.xxx in f-strings for HTML messages. For button text use E.get('name', plain=True).

Usage:
    from bot.helper.ext_utils.emojis import E
    await sendMessage(msg, f"{E.fire} Upload Complete!")
    btns.ibutton(f"{E.get('download', plain=True)} Download", cb)
"""


class _Emoji:
    _MAP = {
        # ── From your custom_emojis.py (verified real IDs) ───────────────
        "magnet":    ("5377535110289576661", "🧲"),
        "sparkle":   ("5325547803936572038", "✨"),
        "party":     ("5235711785482341993", "🎉"),
        "announce":  ("5424818078833715060", "📣"),
        "up_tri":    ("5971972727383264364", "🔺"),
        "diamond":   ("5971944878815317190", "💠"),
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

        # ── Common bot status (best available IDs) ────────────────────────
        "done":      ("5368324170671202286", "✅"),
        "error":     ("5447644880824181073", "❌"),
        "warning":   ("5467406605516091496", "⚠️"),
        "cancel":    ("5381226836808691198", "🚫"),
        "stop":      ("5467406605516091496", "🛑"),
        "mirror":    ("5471952986970267163", "🔄"),
        "restart":   ("5471952986970267163", "🔄"),
        "clock":     ("5301085541559983872", "⏳"),
        "crown":     ("5471952986970267163", "👑"),
        "shield":    ("5445284980978621387", "🛡"),
        "folder":    ("5379748618268510153", "📁"),
        "video":     ("5373123633415074227", "🎥"),
        "zip":       ("5467406605516091496", "📦"),
        "note":      ("5373123633415074227", "📝"),
        "info":      ("5373123633415074227", "ℹ️"),
        "user":      ("5373123633415074227", "👤"),
        "robot":     ("5431815506048155538", "🤖"),
        "speed":     ("5445284980978621387", "⚡"),
        "rocket":    ("5433655514094022326", "🚀"),
    }

    def __getattr__(self, name: str) -> str:
        if name.startswith("_"):
            raise AttributeError(name)
        entry = self._MAP.get(name)
        if entry is None:
            return name
        eid, fallback = entry
        return f'<tg-emoji document_id="{eid}">{fallback}</tg-emoji>'

    def get(self, name: str, plain: bool = False) -> str:
        """Return plain fallback emoji (for button labels) or full HTML tag."""
        entry = self._MAP.get(name)
        if entry is None:
            return name
        eid, fallback = entry
        return fallback if plain else f'<tg-emoji document_id="{eid}">{fallback}</tg-emoji>'


E = _Emoji()
