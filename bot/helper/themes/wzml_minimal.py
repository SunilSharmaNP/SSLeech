#!/usr/bin/env python3
class WZMLStyle:
    # ----------------------
    # async def start(client, message) ---> __main__.py
    ST_BN1_NAME = '👑 ᴏᴡɴᴇʀ '
    ST_BN1_URL = 'https://t.me/Sunil_Sharma_2_0'
    ST_BN2_NAME = '📢 ᴜᴘᴅᴀᴛᴇs'
    ST_BN2_URL = 'https://t.me/SSBotsUpdates'
    ST_MSG = '''<b>🙏 ᴛʜᴀɴᴋs 😇  
ɴᴏᴡ, ɪ ᴡɪʟʟ sᴇɴᴅ ᴀʟʟ ʏᴏᴜʀ ʟᴇᴇᴄʜ/ᴍɪʀʀᴏʀ ғɪʟᴇs & ʟɪɴᴋs ʜᴇʀᴇ.  
sᴛᴀʀᴛ ᴜsɪɴɢ ᴍᴇ ɪɴ ɢʀᴏᴜᴘ ᴀɴᴅ ᴇɴᴊᴏʏ ❤️</b>'''
    ST_BOTPM = """<i>Now, This bot will send all your files and links here. Start Using ...</i>"""
    ST_UNAUTH = """<i>You Are not authorized user! Deploy your own WZML-X Mirror-Leech bot</i>"""
    OWN_TOKEN_GENERATE = (
        """<b>Temporary Token is not yours!</b>\n\n<i>Kindly generate your own.</i>"""
    )
    USED_TOKEN = (
        """<b>Temporary Token already used!</b>\n\n<i>Kindly generate a new one.</i>"""
    )
    LOGGED_PASSWORD = """<b>Bot Already Logged In via Password</b>\n\n<i>No Need to Accept Temp Tokens.</i>"""
    ACTIVATE_BUTTON = "Activate Temporary Token"
    TOKEN_MSG = """<b><u>Generated Temporary Login Token!</u></b>
<b>Temp Token:</b> <code>{token}</code>
<b>Validity:</b> {validity}"""
    # ---------------------
    # async def token_callback(_, query): ---> __main__.py
    ACTIVATED = "✅️ Activated ✅"
    # ---------------------
    # async def login(_, message): --> __main__.py
    LOGGED_IN = "<b>Already Bot Login In!</b>"
    INVALID_PASS = "<b>Invalid Password!</b>\n\nKindly put the correct Password ."
    PASS_LOGGED = "<b>Bot Permanent Login Successfully!</b>"
    LOGIN_USED = "<b>Bot Login Usage :</b>\n\n<code>/cmd [password]</code>"
    # ---------------------
    # async def log(_, message): ---> __main__.py
    LOG_DISPLAY_BT = "📑 Log Display"
    WEB_PASTE_BT = "📨 Web Paste (SB)"
    # ---------------------
    # async def bot_help(client, message): ---> __main__.py
    BASIC_BT = "Basic"
    USER_BT = "Users"
    MICS_BT = "Mics"
    O_S_BT = "Owner & Sudos"
    CLOSE_BT = "Close"
    HELP_HEADER = "㊂ <b><i>Help Guide Menu!</i></b>\n\n<b>NOTE: <i>Click on any CMD to see more minor detalis.</i></b>"

    # async def stats(client, message):
    BOT_STATS = """⌬ <b><i>BOT STATISTICS :</i></b>
┖ <b>Bot Uptime :</b> {bot_uptime}

┎ <b><i>RAM ( MEMORY ) :</i></b>
┃ {ram_bar} {ram}%
┖ <b>U :</b> {ram_u} | <b>F :</b> {ram_f} | <b>T :</b> {ram_t}

┎ <b><i>SWAP MEMORY :</i></b>
┃ {swap_bar} {swap}%
┖ <b>U :</b> {swap_u} | <b>F :</b> {swap_f} | <b>T :</b> {swap_t}

┎ <b><i>DISK :</i></b>
┃ {disk_bar} {disk}%
┃ <b>Total Disk Read :</b> {disk_read}
┃ <b>Total Disk Write :</b> {disk_write}
┖ <b>U :</b> {disk_u} | <b>F :</b> {disk_f} | <b>T :</b> {disk_t}
    
    """
    SYS_STATS = """⌬ <b><i>OS SYSTEM :</i></b>
┠ <b>OS Uptime :</b> {os_uptime}
┠ <b>OS Version :</b> {os_version}
┖ <b>OS Arch :</b> {os_arch}

⌬ <b><i>NETWORK STATS :</i></b>
┠ <b>Upload Data:</b> {up_data}
┠ <b>Download Data:</b> {dl_data}
┠ <b>Pkts Sent:</b> {pkt_sent}k
┠ <b>Pkts Received:</b> {pkt_recv}k
┖ <b>Total I/O Data:</b> {tl_data}

┎ <b>CPU :</b>
┃ {cpu_bar} {cpu}%
┠ <b>CPU Frequency :</b> {cpu_freq}
┠ <b>System Avg Load :</b> {sys_load}
┠ <b>P-Core(s) :</b> {p_core} | <b>V-Core(s) :</b> {v_core}
┠ <b>Total Core(s) :</b> {total_core}
┖ <b>Usable CPU(s) :</b> {cpu_use}
    """
    REPO_STATS = """⌬ <b><i>REPO STATISTICS :</i></b>
┠ <b>Bot Updated :</b> {last_commit}
┠ <b>Current Version :</b> {bot_version}
┠ <b>Latest Version :</b> {lat_version}
┖ <b>Last ChangeLog :</b> {commit_details}

⌬ <b>REMARKS :</b> <code>{remarks}</code>
    """
    BOT_LIMITS = """⌬ <b><i>BOT LIMITATIONS :</i></b>
┠ <b>Direct Limit :</b> {DL} GB
┠ <b>Torrent Limit :</b> {TL} GB
┠ <b>GDrive Limit :</b> {GL} GB
┠ <b>YT-DLP Limit :</b> {YL} GB
┠ <b>Playlist Limit :</b> {PL}
┠ <b>Mega Limit :</b> {ML} GB
┠ <b>Clone Limit :</b> {CL} GB
┖ <b>Leech Limit :</b> {LL} GB

┎ <b>Token Validity :</b> {TV}
┠ <b>User Time Limit :</b> {UTI} / task
┠ <b>User Parallel Tasks :</b> {UT}
┖ <b>Bot Parallel Tasks :</b> {BT}
    """
    # ---------------------

    # async def restart(client, message): ---> __main__.py
    RESTARTING = "<i>Restarting...</i>"
    # ---------------------

    # async def restart_notification(): ---> __main__.py
    RESTART_SUCCESS = """⌬ <b><i>Restarted Successfully!</i></b>
┠ <b>Date:</b> {date}
┠ <b>Time:</b> {time}
┠ <b>TimeZone:</b> {timz}
┖ <b>Version:</b> {version}"""
    RESTARTED = """⌬ <b><i>Bot Restarted!</i></b>"""
    # ---------------------

    # async def ping(client, message): ---> __main__.py
    PING = "<i>Starting Ping..</i>"
    PING_VALUE = "<b>Pong</b>\n<code>{value} ms..</code>"
    # ---------------------

    # async def onDownloadStart(self): --> tasks_listener.py
    LINKS_START = """<b><i>Task Started</i></b>
┠ <b>Mode:</b> {Mode}
┖ <b>By:</b> {Tag}\n\n"""
    LINKS_SOURCE = """➲ <b>Source:</b>
┖ <b>Added On:</b> {On}
------------------------------------------
{Source}
------------------------------------------\n\n"""
    
    
    # async def __msg_to_reply(self): ---> pyrogramEngine.py
    PM_START = "➲ <b><u>Task Started :</u></b>\n┖ <b>Source Link:</b> <a href='{msg_link}'>Click Here</a>"
    L_LOG_START = "➲ <b><u>Leech Started :</u></b>\n┠ <b>User :</b> {mention} ( #ID{uid} )\n┖ <b>Source Link :</b> <a href='{msg_link}'>Click Here</a>"

    # async def onUploadComplete(): ---> tasks_listener.py
    NAME = "<b> 🎥𝐓ɪᴛᴛʟᴇ: {Name}</b>\n┃\n"
    SIZE = "┎ <b>📦 𝐒ɪᴢᴇ: </b>{Size}\n"
    ELAPSE = "┠ <b>⏱️ 𝐄ʟᴀᴘsᴇᴅ: </b>{Time}\n"
    MODE = "┠ <b>🎛️ 𝐌ᴏᴅᴇ: </b>{Mode}\n"

    # ----- LEECH -------
    L_TOTAL_FILES = "┠ <b>🗂️ 𝐓ᴏᴛᴀʟ 𝐅ɪʟᴇs: </b>{Files}\n"
    L_CORRUPTED_FILES = "┠ <b>🛑 𝐂ᴏʀʀᴜᴘᴛᴇᴅ 𝐅ɪʟᴇs: </b>{Corrupt}\n"
    L_CC = "┖ <b> 𝐁ʏ: </b>{Tag}\n\n"
    PM_BOT_MSG = "➲ <b><i>☝️ 𝐅ɪʟᴇ(ꜱ) 𝐡ᴀᴠᴇ ʙᴇᴇɴ 𝐒ᴇɴᴛ ᴀʙᴏᴠᴇ</i></b>"
    L_BOT_MSG = "➲ <b><i>📩 𝐅ɪʟᴇ(ꜱ) 𝐡ᴀᴠᴇ ʙᴇᴇɴ 𝐒ᴇɴᴛ ᴛᴏ 𝐁ᴏᴛ 𝐏𝐌 (𝐏ʀɪᴠᴀᴛᴇ)</i></b>"
    L_LL_MSG = "➲ <b><i>🔗 𝐅ɪʟᴇ(ꜱ) 𝐡ᴀᴠᴇ ʙᴇᴇɴ 𝐒ᴇɴᴛ. 𝐀ᴄᴄᴇss ᴠɪᴀ 𝐋ɪɴᴋs...</i></b>\n"

    M_TYPE = "┠ <b>𝐓ʏᴘᴇ: </b>{Mimetype}\n"
    M_SUBFOLD = "┠ <b>𝐒ᴜʙ𝐅ᴏʟᴅᴇʀs: </b>{Folder}\n"
    TOTAL_FILES = "┠ <b>𝐅ɪʟᴇs: </b>{Files}\n"
    RCPATH = "┠ <b>𝐏ᴀᴛʜ: </b><code>{RCpath}</code>\n"
    M_CC = "┖ <b>𝐁ʏ: </b>{Tag}\n\n"
    M_BOT_MSG = "➲ <b><i>𝐋ɪɴᴋ(s) ʜᴀᴠᴇ ʙᴇᴇɴ 𝐒ᴇɴᴛ ᴛᴏ 𝐁ᴏᴛ 𝐏ᴍ (𝐏ʀɪᴠᴀᴛᴇ)</i></b>"
    # ----- BUTTONS -------
    CLOUD_LINK = "☁️ 𝐂ʟᴏᴜᴅ 𝐋ɪɴᴋ"
    SAVE_MSG = "📨 𝐒ᴀᴠᴇ 𝐌ᴇssᴀɢᴇ"
    RCLONE_LINK = "♻️ 𝐑𝐂ʟᴏɴᴇ 𝐋ɪɴᴋ"
    DDL_LINK = "📎 {Serv} 𝐋ɪɴᴋ"
    SOURCE_URL = "🔐 𝐒ᴏᴜʀᴄᴇ 𝐋ɪɴᴋ"
    INDEX_LINK_F = "🗂 𝐈ɴᴅᴇx 𝐋ɪɴᴋ"
    INDEX_LINK_D = "⚡ 𝐈ɴᴅᴇx 𝐋ɪɴᴋ"
    VIEW_LINK = "🌐 𝐕ɪᴇᴡ 𝐋ɪɴᴋ"
    CHECK_PM = "📥 𝐕ɪᴇᴡ ɪɴ 𝐁ᴏᴛ 𝐏ᴍ"
    CHECK_LL = "🖇 𝐕ɪᴇᴡ ɪɴ 𝐋ɪɴᴋs 𝐋ᴏɢ"
    MEDIAINFO_LINK = "📃 𝐌ᴇᴅɪᴀ𝐈ɴғᴏ"
    SCREENSHOTS = "🖼 𝐒ᴄʀᴇᴇɴ𝐒ʜᴏᴛs"
     # ---------------------


    # def get_readable_message(): ---> bot_utilis.py
    ####--------OVERALL MSG HEADER----------
    STATUS_NAME = "<b><i>🎥𝐓ɪᴛᴛʟᴇ: {Name}</i></b>"

    #####---------PROGRESSIVE STATUS-------
    mm = "┏━━━༻ « <a href=https://t.me/SSBotsUpdates> 𝐒𝐒 𝐁ᴏᴛs</a> » ༺━━━┓"
    BAR = "\n┃ {Bar}"
    PROCESSED = "\n┠ <b>⚡𝐏ʀᴏᴄᴇssᴇᴅ:</b> {Processed}"
    STATUS = '\n┠ <b>🪄𝐒ᴛᴀᴛᴜs:</b> <a href="{Url}">{Status}</a>'
    ETA = " | <b>𝐄ᴛᴀ:</b> {Eta}"
    SPEED = "\n┠ <b>⏳𝐒ᴘᴇᴇᴅ:</b> {Speed}"
    ELAPSED = " | <b>🕓𝐄ʟᴀᴘsᴇᴅ:</b> {Elapsed}"
    ENGINE = "\n┠ <b>🪩𝐄ɴɢɪɴᴇ:</b> {Engine}"
    STA_MODE = "\n┠ <b>🌐𝐌ᴏᴅᴇ:</b> {Mode}"
    SEEDERS = "\n┠ <b>🌱𝐒ᴇᴇᴅᴇʀs:</b> {Seeders}"
    LEECHERS = "\n┠<b>☘️𝐋ᴇᴇᴄʜᴇʀs:</b> {Leechers}"

    ####--------𝐒𝐄𝐄𝐃𝐈𝐍𝐆----------
SEED_SIZE = "\n┠ <b>𝐒ɪᴢᴇ: </b>{Size}"
SEED_SPEED = "\n┠ <b>𝐒ᴘᴇᴇᴅ: </b> {Speed} | "
UPLOADED = "<b>𝐔ᴘʟᴏᴀᴅᴇᴅ: </b> {Upload}"
RATIO = "\n┠ <b>𝐑ᴀᴛɪᴏ: </b> {Ratio} | "
TIME = "<b>𝐓ɪᴍᴇ: </b> {Time}"
SEED_ENGINE = "\n┠ <b>𝐄ɴɢɪɴᴇ:</b> {Engine}"

####--------𝐍ᴏɴ-𝐏ʀᴏɢʀᴇssɪᴠᴇ + 𝐍ᴏɴ 𝐒𝐄𝐄𝐃𝐈𝐍𝐆----------
STATUS_SIZE = "\n┠ <b>𝐒ɪᴢᴇ: </b>{Size}"
NON_ENGINE = "\n┠ <b>𝐄ɴɢɪɴᴇ:</b> {Engine}"

    ####--------OVERALL MSG FOOTER----------
    USER = "\n┠ <b>👤 𝐔sᴇʀ:</b> <code>{User}</code>"
    ID = "\n┠ <b>🆔 𝐈𝐃:</b> <code>{Id}</code>"
    BTSEL = "\n┠ <b>✅ 𝐒ᴇʟᴇᴄᴛ:</b> {Btsel}"
    CANCEL = "\n┠ {Cancel}\n"
    mn = "┗━━━༻ « <a href=https://t.me/SSBotsUpdates> 𝐒𝐒 𝐁ᴏᴛs</a> » ༺━━━┛"

    ####------FOOTER--------
    FOOTER = "┎⌬ <b><i>📊 𝐒𝐒 𝐁ᴏᴛs 𝐒ᴛᴀᴛs</i></b>\n"
    TASKS = "┠ <b>𝐓ᴀsᴋs:</b> {Tasks}\n"
    BOT_TASKS = "┠ <b>𝐓ᴀsᴋs:</b> {Tasks}/{Ttask} | <b>𝐀ᴠʟ:</b> {Free}\n"
    Cpu = "┠ <b> 𝐂ᴘᴜ:</b> {cpu}% | "
    FREE = "<b>𝐅:</b> {free} [{free_p}%]"
    Ram = "\n┠ <b> 𝐑ᴀᴍ:</b> {ram}% | "
    uptime = "<b>𝐔ᴘᴛɪᴍᴇ:</b> {uptime}"
    DL = "\n┖ <b> 𝐃ʟ:</b> {DL}/s | "
    UL = "<b>𝐔ʟ:</b> {UL}/s"

    ###--------BUTTONS-------
    PREVIOUS = "⫷"
    REFRESH = "📄 ᴘᴀɢᴇs\n{Page}"
    NEXT = "⫸"
    # ---------------------

    # STOP_DUPLICATE_MSG: ---> clone.py, aria2_listener.py, task_manager.py
    STOP_DUPLICATE = (
        "📁 𝐅ɪʟᴇ/𝐅ᴏʟᴅᴇʀ ɪs ᴀʟʀᴇᴀᴅʏ ᴀᴠᴀɪʟᴀʙʟᴇ ɪɴ 𝐃ʀɪᴠᴇ.\n 𝐇ᴇʀᴇ ᴀʀᴇ {content} ʟɪsᴛ ʀᴇsᴜʟᴛs:"
    )
    # ---------------------

    # async def countNode(_, message): ----> gd_count.py
COUNT_MSG = "<b>𝐂ᴏᴜɴᴛɪɴɢ:</b> <code>{LINK}</code>"
COUNT_NAME = "<b><i>{COUNT_NAME}</i></b>\n┃\n"
COUNT_SIZE = "┠ <b>𝐒ɪᴢᴇ: </b>{COUNT_SIZE}\n"
COUNT_TYPE = "┠ <b>𝐓ʏᴘᴇ: </b>{COUNT_TYPE}\n"
COUNT_SUB = "┠ <b>𝐒ᴜʙ𝐅ᴏʟᴅᴇʀs: </b>{COUNT_SUB}\n"
COUNT_FILE = "┠ <b>𝐅ɪʟᴇs: </b>{COUNT_FILE}\n"
COUNT_CC = "┖ <b>𝐁ʏ: </b>{COUNT_CC}\n"
# ---------------------

# LIST ---> gd_list.py
LIST_SEARCHING = "<b>𝐒ᴇᴀʀᴄʜɪɴɢ 𝐟ᴏʀ <i>{NAME}</i></b>"
LIST_FOUND = "<b>𝐅ᴏᴜɴᴅ {NO} ʀᴇsᴜʟᴛ 𝐟ᴏʀ <i>{NAME}</i></b>"
LIST_NOT_FOUND = "𝐍ᴏ ʀᴇsᴜʟᴛ 𝐟ᴏᴜɴᴅ 𝐟ᴏʀ <i>{NAME}</i>"
# ---------------------

# async def mirror_status(_, message): ----> status.py
NO_ACTIVE_DL = """<i>𝐍ᴏ 𝐀ᴄᴛɪᴠᴇ 𝐃ᴏᴡɴʟᴏᴀᴅs!</i>
 
⌬ <b><i>𝐁ᴏᴛ 𝐒ᴛᴀᴛs</i></b>
┠ <b>CPU:</b> {cpu}% | <b>F:</b> {free} [{free_p}%]
┖ <b>RAM:</b> {ram} | <b>𝐔ᴘᴛɪᴍᴇ:</b> {uptime}
"""
# ---------------------

# USER Setting --> user_setting.py
USER_SETTING = """㊂ <b><u>𝐔sᴇʀ 𝐒ᴇᴛᴛɪɴɢs :</u></b>
        
┎<b> 𝐍ᴀᴍᴇ :</b> {NAME} ( <code>{ID}</code> )
┠<b> 𝐔sᴇʀɴᴀᴍᴇ :</b> {USERNAME}
┠<b> 𝐓ᴇʟᴇɢʀᴀᴍ 𝐃𝐂 :</b> {DC}
┖<b> 𝐋ᴀɴɢᴜᴀɢᴇ :</b> {LANG}

➲ <u><b>𝐀ᴠᴀɪʟᴀʙʟᴇ 𝐀ʀɢs:</b></u>
• <b>-s</b> or <b>-set</b>: 𝐒ᴇᴛ 𝐃ɪʀᴇᴄᴛʟʏ ᴠɪᴀ 𝐀ʀɢ"""

UNIVERSAL = """㊂ <b><u>𝐔ɴɪᴠᴇʀsᴀʟ 𝐒ᴇᴛᴛɪɴɢs : {NAME}</u></b>

┎<b> 𝐘T-DLP 𝐎ᴘᴛɪᴏɴs :</b> <b><code>{YT}</code></b>
┠<b> 𝐃ᴀɪʟʏ 𝐓ᴀsᴋs :</b> <code>{DT}</code> ᴘᴇʀ ᴅᴀʏ
┠<b> 𝐋ᴀsᴛ 𝐁ᴏᴛ 𝐔sᴇᴅ :</b> <code>{LAST_USED}</code>
┠<b> 𝐔sᴇʀ 𝐒ᴇssɪᴏɴ :</b> <code>{USESS}</code>
┠<b> 𝐌ᴇᴅɪᴀɪɴғᴏ 𝐌ᴏᴅᴇ :</b> <code>{MEDIAINFO}</code>
┠<b> 𝐒ᴀᴠᴇ 𝐌ᴏᴅᴇ :</b> <code>{SAVE_MODE}</code>
┖<b> 𝐔sᴇʀ 𝐁ᴏᴛ 𝐏ᴍ :</b> <code>{BOT_PM}</code>"""

MIRROR = """㊂ <b><u>𝐌ɪʀʀᴏʀ/𝐂ʟᴏɴᴇ 𝐒ᴇᴛᴛɪɴɢs : {NAME}</u></b>

┎<b> 𝐑𝐂ʟᴏɴᴇ 𝐂ᴏɴꜰɪɢ :</b> <i>{RCLONE}</i>
┠<b> 𝐌ɪʀʀᴏʀ 𝐏ʀᴇꜰɪx :</b> <code>{MPREFIX}</code>
┠<b> 𝐌ɪʀʀᴏʀ 𝐒ᴜꜰꜰɪx :</b> <code>{MSUFFIX}</code>
┠<b> 𝐌ɪʀʀᴏʀ 𝐑ᴇᴍɴᴀᴍᴇ :</b> <code>{MREMNAME}</code>
┠<b> 𝐃ᴅʟ 𝐒ᴇʀᴠᴇʀ(s) :</b> <i>{DDL_SERVER}</i>
┠<b> 𝐔sᴇʀ 𝐓ᴅ 𝐌ᴏᴅᴇ :</b> <i>{TMODE}</i>
┠<b> 𝐓ᴏᴛᴀʟ 𝐔sᴇʀ 𝐓ᴅ(s) :</b> <i>{USERTD}</i>
┖<b> 𝐃ᴀɪʟʏ 𝐌ɪʀʀᴏʀ :</b> <code>{DM}</code> ᴘᴇʀ ᴅᴀʏ"""

LEECH = """㊂ <b><u>𝐋ᴇᴇᴄʜ 𝐒ᴇᴛᴛɪɴɢs 𝐟ᴏʀ {NAME}</u></b>

┎<b> 𝐃ᴀɪʟʏ 𝐋ᴇᴇᴄʜ : </b><code>{DL}</code> ᴘᴇʀ ᴅᴀʏ
┠<b> 𝐋ᴇᴇᴄʜ 𝐓ʏᴘᴇ :</b> <i>{LTYPE}</i>
┠<b> 𝐂ᴜsᴛᴏᴍ 𝐓ʜᴜᴍʙɴᴀɪʟ :</b> <i>{THUMB}</i>
┠<b> 𝐋ᴇᴇᴄʜ 𝐒ᴘʟɪᴛ 𝐒ɪᴢᴇ :</b> <code>{SPLIT_SIZE}</code>
┠<b> 𝐄ǫᴜᴀʟ 𝐒ᴘʟɪᴛs :</b> <i>{EQUAL_SPLIT}</i>
┠<b> 𝐌ᴇᴅɪᴀ 𝐆ʀᴏᴜᴘ :</b> <i>{MEDIA_GROUP}</i>
┠<b> 𝐋ᴇᴇᴄʜ 𝐂ᴀᴘᴛɪᴏɴ :</b> <code>{LCAPTION}</code>
┠<b> 𝐋ᴇᴇᴄʜ 𝐏ʀᴇꜰɪx :</b> <code>{LPREFIX}</code>
┠<b> 𝐋ᴇᴇᴄʜ 𝐒ᴜꜰꜰɪx :</b> <code>{LSUFFIX}</code>
┠<b> 𝐋ᴇᴇᴄʜ 𝐃ᴜᴍᴘs :</b> <code>{LDUMP}</code>
┠<b> 𝐋ᴇᴇᴄʜ 𝐑ᴇᴍɴᴀᴍᴇ :</b> <code>{LREMNAME}</code>
┖<b> 𝐋ᴇᴇᴄʜ 𝐌ᴇᴛᴀᴅᴀᴛᴀ :</b> <code>{LMETA}</code>"""
