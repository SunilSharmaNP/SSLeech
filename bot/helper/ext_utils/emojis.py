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
        # ── Verified working IDs (user-confirmed) ───────────────────────────
        "bolt":       ("5456140674028019486", "⚡️"),
        "gear":       ("5341715473882955310", "⚙️"),
        "magnet":     ("5377535110289576661", "🧲"),
        "link":       ("5271604874419647061", "🔗"),
        "download":   ("5443127283898405358", "📥"),
        "upload":     ("5445355530111437729", "📤"),
        "coin":       ("5202064723922670546", "🪙"),
        "takeoff":    ("5201691993775818138", "🛫"),
        "timer":      ("5382194935057372936", "⏱"),
        "fire":       ("5220166546491459639", "🔥"),
        "announce":   ("5424818078833715060", "📣"),
        "megaphone":  ("5424818078833715060", "📢"),
        "mail":       ("5424818078833715060", "📨"),
        "inbox":      ("5443127283898405358", "📩"),
        "gem":        ("5427168083074628963", "💎"),
        "info":       ("5334544901428229844", "ℹ️"),
        "clock":      ("5386367538735104399", "⌛"),
        "globe":      ("5224450179368767019", "🌎"),
        "chart":      ("5190806721286657692", "📊"),
        "speed":      ("5220195537520711716", "⚡️"),
        "rocket":     ("5217880283860194582", "🚀"),
        "crown":      ("5217822164362739968", "👑"),
        "eye":        ("5210956306952758910", "👀"),
        "computer":   ("5193177581888755275", "💻"),
        "cpu":        ("5282843764451195532", "🖥"),
        "heart":      ("6296508771325707891", "❤️"),
        "shield":     ("5197288647275071607", "🛡"),
        "up_tri":     ("5449683594425410231", "🔼"),
        "exchange":   ("5402186569006210455", "💱"),
        "checkmark":  ("5206607081334906820", "✔️"),
        "credit":     ("5445353829304387411", "💳"),
        "arrow_right":("5416117059207572332", "➡️"),
        "arrow_down": ("5406745015365943482", "⬇️"),
        "arrow_up":   ("5449683594425410231", "🔼"),
        "arrow_up_right":("5429651785352501917", "↗️"),
        "question":   ("5206479194388713063", "❓"),
        "question2":  ("5452069934089641166", "❓"),
        "smile":      ("5461117441612462242", "🙂"),
        "plus":       ("5397916757333654639", "➕"),
        "trash":      ("5445267414562389170", "🗑"),
        "thumbs_up":  ("5337080053119336309", "👍"),
        "mic":        ("5294339927318739359", "🎙"),
        "drill":      ("5197371802136892976", "⛏"),
        "exclaim":    ("5219866512961062330", "⁉️"),
        "alarm":      ("5220214598585568818", "🚨"),
        "happy":      ("5440739140347907722", "☺️"),
        "sweat":      ("5217549292205528507", "😰"),
        "cry":        ("5217884424208668349", "😭"),
        "clover":     ("5199658498559854923", "🍀"),
        "fireworks":  ("5215638109068220476", "🎆"),
        "cherry":     ("5222044641200720562", "🌸"),
        "candle":     ("5451882707875276247", "🕯"),
        "love":       ("6298454498884978957", "🫶"),

        # ── Status & result ─────────────────────────────────────────────────
        "done":       ("5368324170671202286", "✅"),
        "error":      ("5447644880824181073", "❌"),
        "warning":    ("5467406605516091496", "⚠️"),
        "cancel":     ("5240241223632954241", "🚫"),
        "stop":       ("5467406605516091496", "🛑"),
        "mirror":     ("5471952986970267163", "🔄"),
        "restart":    ("5471952986970267163", "🔄"),

        # ── Task & progress ─────────────────────────────────────────────────
        "sparkle":    ("5325547803936572038", "✨"),
        "party":      ("5235711785482341993", "🎉"),
        "diamond":    ("5328089410963513796", "💠"),
        "zip":        ("5379763379953803263", "📦"),
        "folder":     ("6026239398650056451", "📁"),
        "openfolder": ("5379763379953803263", "📂"),

        # ── Media & files ────────────────────────────────────────────────────
        "video":      ("5373123633415074227", "🎥"),
        "image":      ("5373123633415074227", "🖼"),
        "note":       ("5373123633415074227", "📝"),
        "file":       ("5373123633415074227", "📄"),
        "log":        ("5373123633415074227", "📑"),

        # ── System stats ─────────────────────────────────────────────────────
        "ram":        ("5193177581888755275", "💻"),
        "disk":       ("5471952986970267163", "💿"),
        "green":      ("5368324170671202286", "🟢"),

        # ── User & identity ──────────────────────────────────────────────────
        "user":       ("5373123633415074227", "👤"),
        "robot":      ("5431815506048155538", "🤖"),

        # ── Misc ─────────────────────────────────────────────────────────────
        "cloud":      ("5471952986970267163", "☁️"),
        "recycle":    ("5471952986970267163", "♻️"),
        "lock":       ("5291873529464122510", "🔐"),
        "unlock":     ("5291873529464122510", "🔓"),
        "search":     ("5471952986970267163", "🔍"),
        "wand":       ("5325547803936572038", "🪄"),
        "pray":       ("5325547803936572038", "🙏"),
        "star":       ("5267500801240092311", "⭐"),
        "explosion":  ("6298644001432012664", "💥"),
        "drop":       ("5393512611968995988", "💧"),
        "dizzy":      ("5469744063815102906", "💫"),
        "bag":        ("5294167145079395967", "🛍"),
        "trending":   ("5244837092042750681", "📈"),
        "phone":      ("5359772714691216710", "📱"),
        "comet":      ("5224607267797606837", "☄️"),
        "chart_down": ("5429518319243775957", "📉"),
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
            return f'<emoji id={eid}>{fallback}</emoji>'
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
