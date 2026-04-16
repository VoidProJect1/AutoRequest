"""
╔══════════════════════════════════════════════════════════════╗
║    🤖  CHANNEL JOIN REQUEST MANAGER BOT  (Pure Telethon)    ║
║   ─────────────────────────────────────────────────────      ║
║   ✅  Python 3.9 Compatible — No errors                     ║
║   📋  Use /admin to access the admin panel                   ║
║   🔐  Default Password: Void#123                             ║
╚══════════════════════════════════════════════════════════════╝

INSTALL:
    pip install telethon

FILL IN before running:
    BOT_TOKEN  → from @BotFather
    API_ID     → from https://my.telegram.org
    API_HASH   → from https://my.telegram.org
"""

import asyncio
import json
import os
import logging
from datetime import datetime
from typing import Optional

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    FloodWaitError,
    UserIsBlockedError,
    InputUserDeactivatedError,
    PhoneCodeInvalidError,
)
from telethon.tl.functions.messages import HideChatJoinRequestRequest
from telethon.tl.types import (
    UpdateBotChatInviteRequester,
    PeerChannel,
    PeerChat,
)

# ───────────────────────────────────────────────────────────
#  ⚠️  FILL IN YOUR VALUES BELOW BEFORE RUNNING
# ───────────────────────────────────────────────────────────
BOT_TOKEN  = "YOUR_BOT_TOKEN_HERE"   # ← from @BotFather
API_ID     = 0                        # ← integer from my.telegram.org
API_HASH   = ""                       # ← string from my.telegram.org
ADMIN_PASS = "Void#123"               # ← change to your own password
# ───────────────────────────────────────────────────────────

DATA_FILE = "bot_data.json"
MEDIA_DIR = "bot_media"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── Data layer ────────────────────────────────────────────

def default_data():
    return {
        "channel_id":     None,
        "channel_title":  "",
        "auto_accept":    False,
        "messages":       [],
        "admin_sessions": [],
        "userbot": {
            "api_id": None, "api_hash": None,
            "session": None, "phone": None,
        },
        "stats": {
            "total_requests": 0, "accepted": 0,
            "ignored": 0, "started_users": [],
        },
    }

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                d = json.load(f)
            base = default_data()
            for k, v in base.items():
                d.setdefault(k, v)
            if not isinstance(d.get("userbot"), dict):
                d["userbot"] = default_data()["userbot"]
            return d
        except Exception:
            pass
    return default_data()

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(DB, f, indent=2, default=str)

DB = load_data()

# ── In-memory state ───────────────────────────────────────
STATE         = {}
PENDING       = {}
USERBOT_SETUP = {}

# ── Clients ───────────────────────────────────────────────
bot     = TelegramClient("bot_session", API_ID, API_HASH)
userbot = None

# ── Helpers ───────────────────────────────────────────────
def is_admin(uid):
    return uid in DB.get("admin_sessions", [])

def toggle_str(v):
    return "✅ ON" if v else "❌ OFF"

def now_str():
    return datetime.now().strftime("%d %b %Y  %H:%M")

def media_filename(uid, kind, ext):
    ts = int(datetime.now().timestamp())
    return os.path.join(MEDIA_DIR, f"{kind}_{uid}_{ts}.{ext}")

def peer_to_full_id(peer):
    if isinstance(peer, PeerChannel):
        return -(1_000_000_000_000 + peer.channel_id)
    if isinstance(peer, PeerChat):
        return -peer.chat_id
    return None

# ── Admin panel keyboard ──────────────────────────────────
def admin_keyboard():
    auto  = DB.get("auto_accept", False)
    ub    = DB.get("userbot", {})
    ub_ok = bool(ub.get("session") and userbot)
    lbl   = "🔄  Update Userbot (Admin Sender)" if ub_ok else "👤  Setup Userbot (Admin Sender) ⚠️"
    return [
        [Button.inline("📢  Set Channel", b"set_channel")],
        [Button.inline(
            "🔄  Auto Accept — ON ✅" if auto else "🔄  Auto Accept — OFF ❌",
            b"toggle_auto",
        )],
        [
            Button.inline("➕  Add Message",   b"add_message"),
            Button.inline("📋  View Messages", b"view_msgs"),
        ],
        [Button.inline("🗑️  Clear All Messages", b"clear_msgs")],
        [Button.inline(lbl, b"setup_userbot")],
        [Button.inline("🗑️  Remove Userbot", b"remove_userbot")],
        [
            Button.inline("🔄  Refresh", b"refresh"),
            Button.inline("🚪  Logout",  b"logout"),
        ],
    ]

async def show_admin_panel(uid):
    ch    = DB.get("channel_title") or "❗ Not Set"
    cid   = DB.get("channel_id")    or "—"
    auto  = DB.get("auto_accept", False)
    nmsg  = len(DB.get("messages", []))
    st    = DB.get("stats", {})
    ub    = DB.get("userbot", {})
    ub_ok = bool(ub.get("session") and userbot)

    text = (
        "👑 **ADMIN CONTROL PANEL**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📢 **Channel:** {ch}\n"
        f"🆔 **Channel ID:** `{cid}`\n"
        f"🤖 **Auto Accept:** {toggle_str(auto)}\n"
        f"📨 **Saved Messages:** {nmsg}\n"
        f"👤 **Userbot (Primary Sender):** "
        f"{'✅ Active — sends as channel admin' if ub_ok else '❌ Not Set (bot fallback only)'}\n\n"
        "📊 **STATISTICS**\n"
        "──────────────────────────\n"
        f"👥 **Bot Users:** {len(st.get('started_users', []))}\n"
        f"📬 **Total Requests:** {st.get('total_requests', 0)}\n"
        f"✅ **Accepted:** {st.get('accepted', 0)}\n"
        f"⏸️ **Ignored:** {st.get('ignored', 0)}\n\n"
        f"🕐 **Updated:** {now_str()}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await bot.send_message(uid, text, buttons=admin_keyboard())

# ── Userbot helpers ───────────────────────────────────────
async def start_userbot():
    global userbot
    ub = DB.get("userbot", {})
    if not (ub.get("session") and ub.get("api_id") and ub.get("api_hash")):
        log.info("Userbot: no saved session — skipping.")
        return False
    try:
        client = TelegramClient(
            StringSession(ub["session"]),
            int(ub["api_id"]),
            ub["api_hash"],
        )
        await client.connect()
        if not await client.is_user_authorized():
            log.warning("Userbot session expired or revoked.")
            return False
        me = await client.get_me()
        userbot = client
        log.info("✅ Userbot ready: @%s (%s)", me.username, me.id)
        return True
    except Exception as e:
        log.error("Userbot start failed: %s", e)
        return False

async def _finish_userbot_session(uid, tg, setup):
    global userbot
    STATE.pop(uid, None)
    USERBOT_SETUP.pop(uid, None)
    try:
        session_str = tg.session.save()
        DB["userbot"] = {
            "api_id":   setup.get("api_id"),
            "api_hash": setup.get("api_hash"),
            "session":  session_str,
            "phone":    setup.get("phone", ""),
        }
        save_data()
        if userbot and userbot is not tg:
            try:
                await userbot.disconnect()
            except Exception:
                pass
        userbot = tg
        me   = await tg.get_me()
        name = (f"{me.first_name or ''} {me.last_name or ''}").strip()
        await bot.send_message(
            uid,
            f"✅ **Userbot Setup Complete!**\n\n"
            f"👤 **Account:** {name}\n"
            f"🆔 **ID:** `{me.id}`\n"
            f"📱 **Username:** @{me.username or 'N/A'}\n\n"
            "Messages will now be sent from this account.\n"
            "⚠️ Make sure this account is also **admin** in your channel.",
        )
        await show_admin_panel(uid)
    except Exception as e:
        await bot.send_message(uid, f"❌ Failed to save session: `{e}`")

# ═══════════════════════════════════════════════════════════
#  BOT EVENT HANDLERS
# ═══════════════════════════════════════════════════════════

# ── /start ────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r"^/start", func=lambda e: e.is_private))
async def cmd_start(event):
    uid = event.sender_id
    started = DB["stats"].setdefault("started_users", [])
    if uid not in started:
        started.append(uid)
        save_data()
    await event.respond(
        "🌟 **Thanks for using our Services!**\n\n"
        "✨ We're glad to have you here.\n"
        "🙏 Your support means everything to us!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💫 _Powered by Channel Manager Bot_",
    )

# ── /admin ────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r"^/admin", func=lambda e: e.is_private))
async def cmd_admin(event):
    uid = event.sender_id
    if is_admin(uid):
        await show_admin_panel(uid)
        return
    STATE[uid] = "await_pass"
    await event.respond(
        "🔐 **Admin Panel — Authentication Required**\n\n"
        "Please send the admin password:",
    )

# ── Text / state machine ──────────────────────────────────
@bot.on(events.NewMessage(func=lambda e: e.is_private and bool(e.text)))
async def on_text(event):
    uid  = event.sender_id
    text = event.text.strip()

    if text.startswith("/start") or text.startswith("/admin"):
        return

    st = STATE.get(uid)

    # ── Password ──────────────────────────────────────────
    if st == "await_pass":
        STATE.pop(uid, None)
        if text == ADMIN_PASS:
            if uid not in DB["admin_sessions"]:
                DB["admin_sessions"].append(uid)
            save_data()
            await event.respond("✅ **Access granted! Welcome, Admin 👑**")
            await show_admin_panel(uid)
        else:
            await event.respond("❌ **Wrong password.**\nUse /admin to try again.")
        return

    if not is_admin(uid):
        return

    # ── Set channel ───────────────────────────────────────
    if st == "set_channel":
        STATE.pop(uid, None)
        try:
            entity = await bot.get_entity(
                int(text) if text.lstrip("-").isdigit() else text
            )
            DB["channel_id"]    = entity.id
            DB["channel_title"] = getattr(entity, "title", text)
            save_data()
            await event.respond(
                f"✅ **Channel set!**\n\n"
                f"📢 **Name:** {DB['channel_title']}\n"
                f"🆔 **ID:** `{entity.id}`",
            )
        except Exception as e:
            await event.respond(
                "❌ **Invalid channel!**\n\n"
                "• Make sure the bot is **admin** in that channel\n"
                "• Use `@username` or numeric ID like `-1001234567890`\n\n"
                f"Error: `{e}`",
            )
        await show_admin_panel(uid)
        return

    # ── Add text step ─────────────────────────────────────
    if st == "add_text":
        PENDING[uid] = {"text": text, "photo_path": None, "audio_path": None}
        STATE[uid] = "add_photo"
        await event.respond(
            "🖼️ **Text saved!**\n\n"
            "Now send a **photo** to attach, or type `/skip` to skip.",
        )
        return

    if st == "add_photo" and text.lower() in ("/skip", "skip"):
        STATE[uid] = "add_audio"
        await event.respond(
            "🎵 Now send an **audio / voice** file, or type `/skip` to finish.",
        )
        return

    if st == "add_audio" and text.lower() in ("/skip", "skip"):
        STATE.pop(uid, None)
        msg_obj = PENDING.pop(uid, None)
        if msg_obj:
            DB["messages"].append(msg_obj)
            save_data()
        await event.respond("✅ **Message saved!**")
        await show_admin_panel(uid)
        return

    # ══ Userbot setup flow ════════════════════════════════

    if st == "ub_api_id":
        if not text.isdigit():
            await event.respond("❌ API ID must be a **number**. Please try again:")
            return
        USERBOT_SETUP[uid] = {"api_id": int(text)}
        STATE[uid] = "ub_api_hash"
        await event.respond("🔑 **Step 2 / 4 — API Hash**\n\nSend your **API Hash** string:")
        return

    if st == "ub_api_hash":
        USERBOT_SETUP.setdefault(uid, {})["api_hash"] = text
        STATE[uid] = "ub_phone"
        await event.respond(
            "📱 **Step 3 / 4 — Phone Number**\n\n"
            "Send with country code, e.g. `+919876543210`:",
        )
        return

    if st == "ub_phone":
        setup = USERBOT_SETUP.get(uid, {})
        if not setup.get("api_id") or not setup.get("api_hash"):
            STATE.pop(uid, None)
            await event.respond("❌ Setup lost. Please start again from /admin.")
            return
        await event.respond("⏳ **Sending OTP to your Telegram…**")
        try:
            tg = TelegramClient(StringSession(), setup["api_id"], setup["api_hash"])
            await tg.connect()
            result = await tg.send_code_request(text)
            USERBOT_SETUP[uid]["phone"]      = text
            USERBOT_SETUP[uid]["client"]     = tg
            USERBOT_SETUP[uid]["phone_hash"] = result.phone_code_hash
            STATE[uid] = "ub_otp"
            await event.respond(
                "📨 **OTP Sent!**\n\n"
                "**Step 4 / 4 — Enter OTP**\n"
                "Type the code you received on Telegram / SMS.\n\n"
                "⚠️ If you have **2FA enabled**, you'll be asked for your "
                "password afterwards.",
            )
        except Exception as e:
            STATE.pop(uid, None)
            USERBOT_SETUP.pop(uid, None)
            await event.respond(f"❌ Failed to send OTP: `{e}`\n\nUse /admin to retry.")
        return

    if st == "ub_otp":
        setup = USERBOT_SETUP.get(uid, {})
        tg    = setup.get("client")
        if not tg:
            STATE.pop(uid, None)
            await event.respond("❌ Session timed out. Use /admin → Setup Userbot to start over.")
            return
        try:
            await tg.sign_in(
                phone=setup["phone"],
                code=text,
                phone_code_hash=setup["phone_hash"],
            )
            await _finish_userbot_session(uid, tg, setup)
        except PhoneCodeInvalidError:
            await event.respond("❌ **Invalid OTP.** Please enter the correct code:")
        except SessionPasswordNeededError:
            STATE[uid] = "ub_2fa"
            await event.respond(
                "🔒 **2FA Password Required**\n\n"
                "Send your Telegram **2-step verification password**:",
            )
        except Exception as e:
            STATE.pop(uid, None)
            USERBOT_SETUP.pop(uid, None)
            await event.respond(f"❌ Sign-in error: `{e}`\n\nUse /admin to retry.")
        return

    if st == "ub_2fa":
        setup = USERBOT_SETUP.get(uid, {})
        tg    = setup.get("client")
        if not tg:
            STATE.pop(uid, None)
            await event.respond("❌ Session timed out. Use /admin to retry.")
            return
        try:
            await tg.sign_in(password=text)
            await _finish_userbot_session(uid, tg, setup)
        except Exception as e:
            STATE.pop(uid, None)
            USERBOT_SETUP.pop(uid, None)
            await event.respond(f"❌ 2FA error: `{e}`\n\nUse /admin to retry.")
        return

# ── Photo handler ─────────────────────────────────────────
@bot.on(events.NewMessage(func=lambda e: e.is_private and bool(e.photo)))
async def on_photo(event):
    uid = event.sender_id
    if not is_admin(uid) or STATE.get(uid) != "add_photo":
        return
    await event.respond("⏳ Saving photo…")
    try:
        path = media_filename(uid, "photo", "jpg")
        await bot.download_media(event.message, path)
        PENDING.setdefault(uid, {"text": "", "photo_path": None, "audio_path": None})
        PENDING[uid]["photo_path"] = path
        STATE[uid] = "add_audio"
        await event.respond(
            "🖼️ **Photo saved!**\n\n"
            "🎵 Now send an **audio / voice** file, or type `/skip` to finish.",
        )
    except Exception as e:
        await event.respond(f"❌ Failed to save photo: `{e}`\nPlease try again.")

# ── Audio / voice handler ─────────────────────────────────
@bot.on(events.NewMessage(func=lambda e: e.is_private and (bool(e.voice) or bool(e.audio))))
async def on_audio(event):
    uid = event.sender_id
    if not is_admin(uid) or STATE.get(uid) != "add_audio":
        return
    await event.respond("⏳ Saving audio…")
    try:
        is_voice = bool(event.voice)
        ext      = "ogg" if is_voice else "mp3"
        path     = media_filename(uid, "voice" if is_voice else "audio", ext)
        await bot.download_media(event.message, path)
        PENDING.setdefault(uid, {"text": "", "photo_path": None, "audio_path": None})
        PENDING[uid]["audio_path"] = path
        STATE.pop(uid, None)
        msg_obj = PENDING.pop(uid, None)
        if msg_obj:
            DB["messages"].append(msg_obj)
            save_data()
        await event.respond("✅ **Message with audio saved!**")
        await show_admin_panel(uid)
    except Exception as e:
        await event.respond(f"❌ Failed to save audio: `{e}`\nPlease try again.")

# ── Callback queries (button presses) ────────────────────
@bot.on(events.CallbackQuery())
async def on_callback(event):
    uid = event.sender_id
    d   = event.data

    if not is_admin(uid):
        await event.answer("❌ Not authorised!", alert=True)
        return

    async def delete_panel():
        try:
            await event.delete()
        except Exception:
            pass

    if d == b"set_channel":
        await event.answer()
        STATE[uid] = "set_channel"
        await delete_panel()
        await bot.send_message(
            uid,
            "📢 **Set Channel**\n\n"
            "Send the channel **username** (e.g. `@mychannel`) or\n"
            "numeric **ID** for private channels (e.g. `-1001234567890`).\n\n"
            "⚠️ The bot must be **admin** in that channel!",
        )

    elif d == b"toggle_auto":
        DB["auto_accept"] = not DB.get("auto_accept", False)
        save_data()
        state = "✅ ENABLED" if DB["auto_accept"] else "❌ DISABLED"
        await event.answer(f"Auto Accept is now {state}", alert=True)
        await delete_panel()
        await show_admin_panel(uid)

    elif d == b"add_message":
        await event.answer()
        STATE[uid] = "add_text"
        await delete_panel()
        await bot.send_message(
            uid,
            "📝 **Add New Message**\n\n"
            "Send the **text** for your message.\n"
            "You will then be asked for an optional photo and audio.\n\n"
            "💡 All saved messages are sent sequentially to each accepted user.",
        )

    elif d == b"view_msgs":
        msgs = DB.get("messages", [])
        if not msgs:
            await event.answer("No messages saved yet!", alert=True)
            return
        await event.answer()
        lines = []
        for i, m in enumerate(msgs, 1):
            t = (m.get("text") or "(no text)")[:60]
            p = " 🖼️" if m.get("photo_path") else ""
            a = " 🎵" if m.get("audio_path") else ""
            lines.append(f"**{i}.** {t}{p}{a}")
        await bot.send_message(
            uid,
            "📋 **Saved Messages:**\n\n" + "\n".join(lines),
        )

    elif d == b"clear_msgs":
        for m in DB.get("messages", []):
            for key in ("photo_path", "audio_path"):
                p = m.get(key)
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        DB["messages"] = []
        save_data()
        await event.answer("🗑️ All messages cleared!", alert=True)
        await delete_panel()
        await show_admin_panel(uid)

    elif d == b"refresh":
        await event.answer("🔄 Refreshed!")
        await delete_panel()
        await show_admin_panel(uid)

    elif d == b"logout":
        if uid in DB["admin_sessions"]:
            DB["admin_sessions"].remove(uid)
        save_data()
        await event.answer("👋 Logged out!", alert=True)
        await delete_panel()
        await bot.send_message(
            uid,
            "🚪 **Logged out successfully.**\n"
            "Use /admin to log in again.",
        )

    elif d == b"setup_userbot":
        await event.answer()
        STATE[uid] = "ub_api_id"
        USERBOT_SETUP.pop(uid, None)
        await delete_panel()
        await bot.send_message(
            uid,
            "👤 **Setup Userbot — Channel Admin DM Bridge**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "The userbot is the **main sender** for all welcome messages.\n"
            "Since it is a channel admin, Telegram will show:\n"
            "  `[Account Name] is admin of [Your Channel]`\n"
            "on every message — bypassing the normal DM limits.\n\n"
            "📋 Get API credentials: https://my.telegram.org\n\n"
            "⚠️ The account you add **MUST be admin** in your channel.\n\n"
            "**Step 1 / 4 — API ID**\n"
            "Send your **API ID** (numbers only):",
        )

    elif d == b"remove_userbot":
        global userbot
        if userbot:
            try:
                await userbot.disconnect()
            except Exception:
                pass
            userbot = None
        DB["userbot"] = {
            "api_id": None, "api_hash": None,
            "session": None, "phone": None,
        }
        save_data()
        await event.answer("✅ Userbot removed!", alert=True)
        await delete_panel()
        await show_admin_panel(uid)

    else:
        await event.answer("Unknown action.", alert=True)

# ── Join request handler ──────────────────────────────────
@bot.on(events.Raw(UpdateBotChatInviteRequester))
async def on_join_request(update):
    uid  = update.user_id
    peer = update.peer

    DB["stats"]["total_requests"] = DB["stats"].get("total_requests", 0) + 1

    cfg_ch = DB.get("channel_id")
    if cfg_ch:
        incoming_id = peer_to_full_id(peer)
        bare_id = getattr(peer, "channel_id", None) or getattr(peer, "chat_id", None)
        if (
            str(incoming_id) != str(cfg_ch)
            and str(bare_id) != str(cfg_ch)
        ):
            save_data()
            return

    if not DB.get("auto_accept", False):
        DB["stats"]["ignored"] = DB["stats"].get("ignored", 0) + 1
        save_data()
        log.info("⏸  Auto-accept OFF — ignored %s", uid)
        return

    # ── Approve the join request ──────────────────────────
    try:
        await bot(HideChatJoinRequestRequest(peer=peer, user_id=uid, approved=True))
        DB["stats"]["accepted"] = DB["stats"].get("accepted", 0) + 1
        save_data()
        log.info("✅ Approved %s", uid)
    except FloodWaitError as fw:
        await asyncio.sleep(fw.seconds + 1)
        try:
            await bot(HideChatJoinRequestRequest(peer=peer, user_id=uid, approved=True))
        except Exception as e:
            log.error("Retry approve failed for %s: %s", uid, e)
            return
    except Exception as e:
        log.error("Approve error for %s: %s", uid, e)
        save_data()
        return

    # ── Send welcome messages ─────────────────────────────
    messages = DB.get("messages", [])
    if not messages:
        return

    await asyncio.sleep(1)

    for msg in messages:
        txt        = msg.get("text")       or ""
        photo_path = msg.get("photo_path") or None
        audio_path = msg.get("audio_path") or None
        sent       = False

        # PRIMARY: userbot (channel admin) sends DM.
        # Telegram shows "[Account] is admin of [Channel]" badge.
        # Works even if user never started the bot.
        if userbot:
            try:
                if photo_path and os.path.exists(photo_path):
                    await userbot.send_file(uid, photo_path, caption=txt or "")
                elif txt:
                    await userbot.send_message(uid, txt)

                if audio_path and os.path.exists(audio_path):
                    await userbot.send_file(
                        uid, audio_path,
                        voice_note=audio_path.endswith(".ogg"),
                    )
                sent = True
                log.info("📨 Userbot (admin) DM sent to %s", uid)

            except FloodWaitError as fw:
                log.warning("Userbot FloodWait %ss for %s — retrying", fw.seconds, uid)
                await asyncio.sleep(fw.seconds + 1)
                try:
                    if photo_path and os.path.exists(photo_path):
                        await userbot.send_file(uid, photo_path, caption=txt or "")
                    elif txt:
                        await userbot.send_message(uid, txt)
                    if audio_path and os.path.exists(audio_path):
                        await userbot.send_file(
                            uid, audio_path,
                            voice_note=audio_path.endswith(".ogg"),
                        )
                    sent = True
                    log.info("📨 Userbot DM sent to %s after retry", uid)
                except Exception as e:
                    log.error("Userbot retry failed for %s: %s", uid, e)

            except UserIsBlockedError:
                log.warning("Userbot: user %s blocked the userbot account", uid)
                sent = True

            except InputUserDeactivatedError:
                log.warning("Userbot: user %s account is deactivated", uid)
                sent = True

            except Exception as e:
                log.error("Userbot DM error for %s: %s", uid, e)

        # FALLBACK: bot account (only works if user started the bot before)
        if not sent:
            log.info("Falling back to bot DM for %s", uid)
            try:
                if photo_path and os.path.exists(photo_path):
                    await bot.send_file(uid, photo_path, caption=txt or None)
                elif txt:
                    await bot.send_message(uid, txt)

                if audio_path and os.path.exists(audio_path):
                    await bot.send_file(
                        uid, audio_path,
                        voice_note=audio_path.endswith(".ogg"),
                    )
                sent = True
                log.info("📨 Bot DM sent to %s", uid)

            except (UserIsBlockedError, InputUserDeactivatedError):
                log.warning("Bot: cannot DM %s — blocked or deactivated", uid)
            except FloodWaitError as fw:
                await asyncio.sleep(fw.seconds + 1)
            except Exception as e:
                log.warning("Bot DM failed for %s: %s", uid, e)

        if not sent:
            log.warning("⚠️  All DM methods failed for %s", uid)

        await asyncio.sleep(0.6)


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
async def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not BOT_TOKEN:
        print("❌  ERROR: Set BOT_TOKEN at the top of the script.")
        return
    if not API_ID:
        print("❌  ERROR: Set API_ID at the top of the script.")
        return
    if not API_HASH:
        print("❌  ERROR: Set API_HASH at the top of the script.")
        return

    os.makedirs(MEDIA_DIR, exist_ok=True)

    print("""
╔══════════════════════════════════════════════════════════════╗
║    🤖  CHANNEL JOIN REQUEST MANAGER BOT  (Pure Telethon)    ║
║   ─────────────────────────────────────────────────────      ║
║   ✅  Starting up...                                         ║
║   📋  Use /admin to access the admin panel                   ║
║   🔐  Default Password: Void#123                             ║
╚══════════════════════════════════════════════════════════════╝
""")

    ub_ok = await start_userbot()
    if ub_ok:
        print("👤  Userbot: ACTIVE (sends as channel admin)")
    else:
        print("👤  Userbot: not configured  (use /admin → Setup Userbot)")

    await bot.start(bot_token=BOT_TOKEN)
    me = await bot.get_me()
    print(f"✅  Bot started as @{me.username} (ID: {me.id})")
    print("📡  Listening for join requests…")
    print("─" * 55)

    await bot.run_until_disconnected()


if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n🛑  Stopped by user.")
    finally:
        try:
            loop.close()
        except Exception:
            pass
