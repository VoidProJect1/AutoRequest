"""
╔══════════════════════════════════════════════════════════════╗
║    🤖  CHANNEL JOIN REQUEST MANAGER BOT                     ║
║   ─────────────────────────────────────────────────────      ║
║   ✅  python-telegram-bot  (NO API_ID / API_HASH needed)    ║
║   📋  Use /admin to access the admin panel                   ║
║   🔐  Default Password: Void#123                             ║
╚══════════════════════════════════════════════════════════════╝

INSTALL:
    pip install python-telegram-bot telethon

FILL IN before running:
    BOT_TOKEN  →  from @BotFather   (only this one line!)
"""

import asyncio
import json
import os
import logging
from datetime import datetime
from typing import Optional

# ── python-telegram-bot ───────────────────────────────────
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode
from telegram.error import TelegramError

# ── Telethon  (userbot only — no API creds in this script) ─
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    FloodWaitError,
    UserIsBlockedError,
    InputUserDeactivatedError,
    PhoneCodeInvalidError,
)

# ═══════════════════════════════════════════════════════════
#  ⚠️  ONLY FILL IN THESE TWO VALUES  ⚠️
# ═══════════════════════════════════════════════════════════
BOT_TOKEN  = "YOUR_BOT_TOKEN_HERE"   # ← paste your token from @BotFather
ADMIN_PASS = "Void#123"               # ← change to your own password
# ═══════════════════════════════════════════════════════════

DATA_FILE = "bot_data.json"
MEDIA_DIR = "bot_media"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── Global userbot client ─────────────────────────────────
userbot: Optional[TelegramClient] = None

# ── In-memory state dicts ─────────────────────────────────
STATE:         dict = {}   # uid -> current state name
PENDING:       dict = {}   # uid -> message being built
USERBOT_SETUP: dict = {}   # uid -> userbot setup data

# ══════════════════════════════════════════════════════════
#  DATA LAYER
# ══════════════════════════════════════════════════════════

def default_data() -> dict:
    return {
        "channel_id":     None,
        "channel_title":  "",
        "auto_accept":    False,
        "messages":       [],
        "admin_sessions": [],
        "userbot": {
            "api_id":   None,
            "api_hash": None,
            "session":  None,
            "phone":    None,
        },
        "stats": {
            "total_requests": 0,
            "accepted":       0,
            "ignored":        0,
            "started_users":  [],
        },
    }

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
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

def save_data() -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(DB, f, indent=2, default=str)

DB = load_data()

# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════

def is_admin(uid: int) -> bool:
    return uid in DB.get("admin_sessions", [])

def toggle_str(v: bool) -> str:
    return "✅ ON" if v else "❌ OFF"

def now_str() -> str:
    return datetime.now().strftime("%d %b %Y  %H:%M")

def media_filename(uid: int, kind: str, ext: str) -> str:
    os.makedirs(MEDIA_DIR, exist_ok=True)
    ts = int(datetime.now().timestamp())
    return os.path.join(MEDIA_DIR, f"{kind}_{uid}_{ts}.{ext}")

# ══════════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════════

def admin_keyboard() -> InlineKeyboardMarkup:
    auto  = DB.get("auto_accept", False)
    ub    = DB.get("userbot", {})
    ub_ok = bool(ub.get("session") and userbot)
    ub_lbl = "🔄 Update Userbot" if ub_ok else "👤 Setup Userbot ⚠️"

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Set Channel", callback_data="set_channel")],
        [InlineKeyboardButton(
            "🔄 Auto Accept — ON ✅" if auto else "🔄 Auto Accept — OFF ❌",
            callback_data="toggle_auto",
        )],
        [
            InlineKeyboardButton("➕ Add Message",    callback_data="add_message"),
            InlineKeyboardButton("📋 View Messages",  callback_data="view_msgs"),
        ],
        [InlineKeyboardButton("🗑️ Clear All Messages", callback_data="clear_msgs")],
        [InlineKeyboardButton(ub_lbl, callback_data="setup_userbot")],
        [InlineKeyboardButton("🗑️ Remove Userbot", callback_data="remove_userbot")],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh"),
            InlineKeyboardButton("🚪 Logout",  callback_data="logout"),
        ],
    ])

async def send_admin_panel(bot, uid: int) -> None:
    ch    = DB.get("channel_title") or "❗ Not Set"
    cid   = DB.get("channel_id")    or "—"
    auto  = DB.get("auto_accept", False)
    nmsg  = len(DB.get("messages", []))
    st    = DB.get("stats", {})
    ub    = DB.get("userbot", {})
    ub_ok = bool(ub.get("session") and userbot)

    text = (
        "👑 <b>ADMIN CONTROL PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📢 <b>Channel:</b> {ch}\n"
        f"🆔 <b>Channel ID:</b> <code>{cid}</code>\n"
        f"🤖 <b>Auto Accept:</b> {toggle_str(auto)}\n"
        f"📨 <b>Saved Messages:</b> {nmsg}\n"
        f"👤 <b>Userbot:</b> "
        + ("✅ Active — sends as channel admin" if ub_ok else "❌ Not Set (bot fallback only)")
        + "\n\n"
        "📊 <b>STATISTICS</b>\n"
        "──────────────────────────\n"
        f"👥 <b>Bot Users:</b> {len(st.get('started_users', []))}\n"
        f"📬 <b>Total Requests:</b> {st.get('total_requests', 0)}\n"
        f"✅ <b>Accepted:</b> {st.get('accepted', 0)}\n"
        f"⏸️ <b>Ignored:</b> {st.get('ignored', 0)}\n\n"
        f"🕐 <b>Updated:</b> {now_str()}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await bot.send_message(
        uid, text,
        reply_markup=admin_keyboard(),
        parse_mode=ParseMode.HTML,
    )

# ══════════════════════════════════════════════════════════
#  USERBOT (TELETHON)
# ══════════════════════════════════════════════════════════

async def start_userbot() -> bool:
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
        log.info("✅ Userbot ready: @%s (ID: %s)", me.username, me.id)
        return True
    except Exception as e:
        log.error("Userbot start failed: %s", e)
        return False

async def finish_userbot_session(
    bot, uid: int, tg: TelegramClient, setup: dict
) -> None:
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
            f"✅ <b>Userbot Setup Complete!</b>\n\n"
            f"👤 <b>Account:</b> {name}\n"
            f"🆔 <b>ID:</b> <code>{me.id}</code>\n"
            f"📱 <b>Username:</b> @{me.username or 'N/A'}\n\n"
            "Messages will now be sent from this account.\n"
            "⚠️ Make sure this account is also <b>admin</b> in your channel.",
            parse_mode=ParseMode.HTML,
        )
        await send_admin_panel(bot, uid)
    except Exception as e:
        await bot.send_message(
            uid,
            f"❌ Failed to save session: <code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )

# ══════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ══════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    started = DB["stats"].setdefault("started_users", [])
    if uid not in started:
        started.append(uid)
        save_data()
    await update.message.reply_text(
        "🌟 <b>Thanks for using our Services!</b>\n\n"
        "✨ We're glad to have you here.\n"
        "🙏 Your support means everything to us!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💫 <i>Powered by Channel Manager Bot</i>",
        parse_mode=ParseMode.HTML,
    )

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if is_admin(uid):
        await send_admin_panel(context.bot, uid)
        return
    STATE[uid] = "await_pass"
    await update.message.reply_text(
        "🔐 <b>Admin Panel — Authentication Required</b>\n\n"
        "Please send the admin password:",
        parse_mode=ParseMode.HTML,
    )

# ══════════════════════════════════════════════════════════
#  TEXT / STATE MACHINE HANDLER
# ══════════════════════════════════════════════════════════

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid  = update.effective_user.id
    text = update.message.text.strip()

    # Don't re-process commands
    if text.startswith("/"):
        return

    st = STATE.get(uid)

    # ── Password ──────────────────────────────────────────
    if st == "await_pass":
        STATE.pop(uid, None)
        if text == ADMIN_PASS:
            if uid not in DB["admin_sessions"]:
                DB["admin_sessions"].append(uid)
            save_data()
            await update.message.reply_text(
                "✅ <b>Access granted! Welcome, Admin 👑</b>",
                parse_mode=ParseMode.HTML,
            )
            await send_admin_panel(context.bot, uid)
        else:
            await update.message.reply_text(
                "❌ <b>Wrong password.</b>\nUse /admin to try again.",
                parse_mode=ParseMode.HTML,
            )
        return

    if not is_admin(uid):
        return

    # ── Set channel ───────────────────────────────────────
    if st == "set_channel":
        STATE.pop(uid, None)
        try:
            try:
                chat_ref = int(text) if text.lstrip("-").isdigit() else text
            except ValueError:
                chat_ref = text
            chat = await context.bot.get_chat(chat_ref)
            DB["channel_id"]    = chat.id
            DB["channel_title"] = chat.title or text
            save_data()
            await update.message.reply_text(
                f"✅ <b>Channel set!</b>\n\n"
                f"📢 <b>Name:</b> {DB['channel_title']}\n"
                f"🆔 <b>ID:</b> <code>{chat.id}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            await update.message.reply_text(
                "❌ <b>Invalid channel!</b>\n\n"
                "• Make sure the bot is <b>admin</b> in that channel\n"
                "• Use <code>@username</code> or numeric ID like "
                "<code>-1001234567890</code>\n\n"
                f"Error: <code>{e}</code>",
                parse_mode=ParseMode.HTML,
            )
        await send_admin_panel(context.bot, uid)
        return

    # ── Add message — text step ───────────────────────────
    if st == "add_text":
        PENDING[uid] = {"text": text, "photo_path": None, "audio_path": None}
        STATE[uid] = "add_photo"
        await update.message.reply_text(
            "🖼️ <b>Text saved!</b>\n\n"
            "Now send a <b>photo</b> to attach, or type /skip to skip.",
            parse_mode=ParseMode.HTML,
        )
        return

    if st == "add_photo" and text.lower() in ("/skip", "skip"):
        STATE[uid] = "add_audio"
        await update.message.reply_text(
            "🎵 Now send an <b>audio / voice</b> file, or type /skip to finish.",
            parse_mode=ParseMode.HTML,
        )
        return

    if st == "add_audio" and text.lower() in ("/skip", "skip"):
        STATE.pop(uid, None)
        msg_obj = PENDING.pop(uid, None)
        if msg_obj:
            DB["messages"].append(msg_obj)
            save_data()
        await update.message.reply_text(
            "✅ <b>Message saved!</b>",
            parse_mode=ParseMode.HTML,
        )
        await send_admin_panel(context.bot, uid)
        return

    # ══ Userbot setup flow ════════════════════════════════

    if st == "ub_api_id":
        if not text.isdigit():
            await update.message.reply_text(
                "❌ API ID must be a <b>number</b>. Please try again:",
                parse_mode=ParseMode.HTML,
            )
            return
        USERBOT_SETUP[uid] = {"api_id": int(text)}
        STATE[uid] = "ub_api_hash"
        await update.message.reply_text(
            "🔑 <b>Step 2/4 — API Hash</b>\n\nSend your <b>API Hash</b> string:",
            parse_mode=ParseMode.HTML,
        )
        return

    if st == "ub_api_hash":
        USERBOT_SETUP.setdefault(uid, {})["api_hash"] = text
        STATE[uid] = "ub_phone"
        await update.message.reply_text(
            "📱 <b>Step 3/4 — Phone Number</b>\n\n"
            "Send with country code, e.g. <code>+919876543210</code>:",
            parse_mode=ParseMode.HTML,
        )
        return

    if st == "ub_phone":
        setup = USERBOT_SETUP.get(uid, {})
        if not setup.get("api_id") or not setup.get("api_hash"):
            STATE.pop(uid, None)
            await update.message.reply_text(
                "❌ Setup data lost. Please start again from /admin.",
            )
            return
        await update.message.reply_text(
            "⏳ <b>Sending OTP to your Telegram…</b>",
            parse_mode=ParseMode.HTML,
        )
        try:
            tg = TelegramClient(
                StringSession(),
                setup["api_id"],
                setup["api_hash"],
            )
            await tg.connect()
            result = await tg.send_code_request(text)
            USERBOT_SETUP[uid]["phone"]      = text
            USERBOT_SETUP[uid]["client"]     = tg
            USERBOT_SETUP[uid]["phone_hash"] = result.phone_code_hash
            STATE[uid] = "ub_otp"
            await update.message.reply_text(
                "📨 <b>OTP Sent!</b>\n\n"
                "<b>Step 4/4 — Enter OTP</b>\n"
                "Type the code you received on Telegram / SMS.\n\n"
                "⚠️ If you have <b>2FA enabled</b>, you'll be asked for "
                "your password afterwards.",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            STATE.pop(uid, None)
            USERBOT_SETUP.pop(uid, None)
            await update.message.reply_text(
                f"❌ Failed to send OTP: <code>{e}</code>\n\nUse /admin to retry.",
                parse_mode=ParseMode.HTML,
            )
        return

    if st == "ub_otp":
        setup = USERBOT_SETUP.get(uid, {})
        tg    = setup.get("client")
        if not tg:
            STATE.pop(uid, None)
            await update.message.reply_text(
                "❌ Session timed out. Use /admin → Setup Userbot to start over.",
            )
            return
        try:
            await tg.sign_in(
                phone=setup["phone"],
                code=text,
                phone_code_hash=setup["phone_hash"],
            )
            await finish_userbot_session(context.bot, uid, tg, setup)
        except PhoneCodeInvalidError:
            await update.message.reply_text(
                "❌ <b>Invalid OTP.</b> Please enter the correct code:",
                parse_mode=ParseMode.HTML,
            )
        except SessionPasswordNeededError:
            STATE[uid] = "ub_2fa"
            await update.message.reply_text(
                "🔒 <b>2FA Password Required</b>\n\n"
                "Send your Telegram <b>2-step verification password</b>:",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            STATE.pop(uid, None)
            USERBOT_SETUP.pop(uid, None)
            await update.message.reply_text(
                f"❌ Sign-in error: <code>{e}</code>\n\nUse /admin to retry.",
                parse_mode=ParseMode.HTML,
            )
        return

    if st == "ub_2fa":
        setup = USERBOT_SETUP.get(uid, {})
        tg    = setup.get("client")
        if not tg:
            STATE.pop(uid, None)
            await update.message.reply_text(
                "❌ Session timed out. Use /admin to retry.",
            )
            return
        try:
            await tg.sign_in(password=text)
            await finish_userbot_session(context.bot, uid, tg, setup)
        except Exception as e:
            STATE.pop(uid, None)
            USERBOT_SETUP.pop(uid, None)
            await update.message.reply_text(
                f"❌ 2FA error: <code>{e}</code>\n\nUse /admin to retry.",
                parse_mode=ParseMode.HTML,
            )
        return

# ══════════════════════════════════════════════════════════
#  PHOTO HANDLER
# ══════════════════════════════════════════════════════════

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_admin(uid) or STATE.get(uid) != "add_photo":
        return
    await update.message.reply_text("⏳ Saving photo…")
    try:
        path  = media_filename(uid, "photo", "jpg")
        photo = update.message.photo[-1]             # largest size
        tg_file = await context.bot.get_file(photo.file_id)
        await tg_file.download_to_drive(path)
        PENDING.setdefault(uid, {"text": "", "photo_path": None, "audio_path": None})
        PENDING[uid]["photo_path"] = path
        STATE[uid] = "add_audio"
        await update.message.reply_text(
            "🖼️ <b>Photo saved!</b>\n\n"
            "🎵 Now send an <b>audio / voice</b> file, or type /skip to finish.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Failed to save photo: <code>{e}</code>\nPlease try again.",
            parse_mode=ParseMode.HTML,
        )

# ══════════════════════════════════════════════════════════
#  AUDIO / VOICE HANDLER
# ══════════════════════════════════════════════════════════

async def on_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    if not is_admin(uid) or STATE.get(uid) != "add_audio":
        return
    await update.message.reply_text("⏳ Saving audio…")
    try:
        is_voice  = bool(update.message.voice)
        ext       = "ogg" if is_voice else "mp3"
        path      = media_filename(uid, "voice" if is_voice else "audio", ext)
        media_obj = update.message.voice or update.message.audio
        tg_file   = await context.bot.get_file(media_obj.file_id)
        await tg_file.download_to_drive(path)
        PENDING.setdefault(uid, {"text": "", "photo_path": None, "audio_path": None})
        PENDING[uid]["audio_path"] = path
        STATE.pop(uid, None)
        msg_obj = PENDING.pop(uid, None)
        if msg_obj:
            DB["messages"].append(msg_obj)
            save_data()
        await update.message.reply_text(
            "✅ <b>Message with audio saved!</b>",
            parse_mode=ParseMode.HTML,
        )
        await send_admin_panel(context.bot, uid)
    except Exception as e:
        await update.message.reply_text(
            f"❌ Failed to save audio: <code>{e}</code>\nPlease try again.",
            parse_mode=ParseMode.HTML,
        )

# ══════════════════════════════════════════════════════════
#  CALLBACK QUERY (BUTTON PRESS) HANDLER
# ══════════════════════════════════════════════════════════

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global userbot
    query = update.callback_query
    uid   = query.from_user.id
    d     = query.data

    if not is_admin(uid):
        await query.answer("❌ Not authorised!", show_alert=True)
        return

    async def delete_panel() -> None:
        try:
            await query.message.delete()
        except Exception:
            pass

    # ── Set Channel ───────────────────────────────────────
    if d == "set_channel":
        await query.answer()
        STATE[uid] = "set_channel"
        await delete_panel()
        await context.bot.send_message(
            uid,
            "📢 <b>Set Channel</b>\n\n"
            "Send the channel <b>username</b> (e.g. <code>@mychannel</code>) or\n"
            "numeric <b>ID</b> for private channels "
            "(e.g. <code>-1001234567890</code>).\n\n"
            "⚠️ The bot must be <b>admin</b> in that channel!",
            parse_mode=ParseMode.HTML,
        )

    # ── Toggle Auto-Accept ────────────────────────────────
    elif d == "toggle_auto":
        DB["auto_accept"] = not DB.get("auto_accept", False)
        save_data()
        state_label = "✅ ENABLED" if DB["auto_accept"] else "❌ DISABLED"
        await query.answer(f"Auto Accept is now {state_label}", show_alert=True)
        await delete_panel()
        await send_admin_panel(context.bot, uid)

    # ── Add Message ───────────────────────────────────────
    elif d == "add_message":
        await query.answer()
        STATE[uid] = "add_text"
        await delete_panel()
        await context.bot.send_message(
            uid,
            "📝 <b>Add New Message</b>\n\n"
            "Send the <b>text</b> for your message.\n"
            "You will then be asked for an optional photo and audio.\n\n"
            "💡 All saved messages are sent sequentially to each accepted user.",
            parse_mode=ParseMode.HTML,
        )

    # ── View Messages ─────────────────────────────────────
    elif d == "view_msgs":
        msgs = DB.get("messages", [])
        if not msgs:
            await query.answer("No messages saved yet!", show_alert=True)
            return
        await query.answer()
        lines = []
        for i, m in enumerate(msgs, 1):
            t = (m.get("text") or "(no text)")[:60]
            p = " 🖼️" if m.get("photo_path") else ""
            a = " 🎵" if m.get("audio_path") else ""
            lines.append(f"<b>{i}.</b> {t}{p}{a}")
        await context.bot.send_message(
            uid,
            "📋 <b>Saved Messages:</b>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )

    # ── Clear Messages ────────────────────────────────────
    elif d == "clear_msgs":
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
        await query.answer("🗑️ All messages cleared!", show_alert=True)
        await delete_panel()
        await send_admin_panel(context.bot, uid)

    # ── Refresh ───────────────────────────────────────────
    elif d == "refresh":
        await query.answer("🔄 Refreshed!")
        await delete_panel()
        await send_admin_panel(context.bot, uid)

    # ── Logout ────────────────────────────────────────────
    elif d == "logout":
        if uid in DB["admin_sessions"]:
            DB["admin_sessions"].remove(uid)
        save_data()
        await query.answer("👋 Logged out!", show_alert=True)
        await delete_panel()
        await context.bot.send_message(
            uid,
            "🚪 <b>Logged out successfully.</b>\n"
            "Use /admin to log in again.",
            parse_mode=ParseMode.HTML,
        )

    # ── Setup Userbot ─────────────────────────────────────
    elif d == "setup_userbot":
        await query.answer()
        STATE[uid] = "ub_api_id"
        USERBOT_SETUP.pop(uid, None)
        await delete_panel()
        await context.bot.send_message(
            uid,
            "👤 <b>Setup Userbot — Channel Admin DM Bridge</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "The userbot is the <b>main sender</b> for all welcome messages.\n"
            "Since it is a channel admin, Telegram will show:\n"
            "  <code>[Account Name] is admin of [Your Channel]</code>\n"
            "on every message — bypassing normal DM limits.\n\n"
            "📋 Get API credentials: https://my.telegram.org\n\n"
            "⚠️ The account you add <b>MUST be admin</b> in your channel.\n\n"
            "<b>Step 1/4 — API ID</b>\n"
            "Send your <b>API ID</b> (numbers only):",
            parse_mode=ParseMode.HTML,
        )

    # ── Remove Userbot ────────────────────────────────────
    elif d == "remove_userbot":
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
        await query.answer("✅ Userbot removed!", show_alert=True)
        await delete_panel()
        await send_admin_panel(context.bot, uid)

    else:
        await query.answer("Unknown action.", show_alert=True)

# ══════════════════════════════════════════════════════════
#  JOIN REQUEST HANDLER
# ══════════════════════════════════════════════════════════

async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    join_req = update.chat_join_request
    if not join_req:
        return

    uid     = join_req.from_user.id
    chat_id = join_req.chat.id

    DB["stats"]["total_requests"] = DB["stats"].get("total_requests", 0) + 1

    # Filter: only handle the configured channel
    cfg_ch = DB.get("channel_id")
    if cfg_ch and str(chat_id) != str(cfg_ch):
        save_data()
        return

    if not DB.get("auto_accept", False):
        DB["stats"]["ignored"] = DB["stats"].get("ignored", 0) + 1
        save_data()
        log.info("⏸  Auto-accept OFF — ignored user %s", uid)
        return

    # ── Approve the join request ──────────────────────────
    try:
        await context.bot.approve_chat_join_request(chat_id=chat_id, user_id=uid)
        DB["stats"]["accepted"] = DB["stats"].get("accepted", 0) + 1
        save_data()
        log.info("✅ Approved join request from %s", uid)
    except TelegramError as e:
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

        # PRIMARY: userbot (channel admin) — shows admin badge
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
                log.info("📨 Userbot DM sent to %s", uid)

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
                log.warning("Userbot: user %s has blocked the userbot", uid)
                sent = True   # blocked = no point retrying
            except InputUserDeactivatedError:
                log.warning("Userbot: user %s account is deactivated", uid)
                sent = True
            except Exception as e:
                log.error("Userbot DM error for %s: %s", uid, e)

        # FALLBACK: bot account (only works if user has started the bot)
        if not sent:
            log.info("Falling back to bot DM for %s", uid)
            try:
                if photo_path and os.path.exists(photo_path):
                    with open(photo_path, "rb") as fh:
                        await context.bot.send_photo(
                            uid, fh, caption=txt or None
                        )
                elif txt:
                    await context.bot.send_message(uid, txt)

                if audio_path and os.path.exists(audio_path):
                    with open(audio_path, "rb") as fh:
                        if audio_path.endswith(".ogg"):
                            await context.bot.send_voice(uid, fh)
                        else:
                            await context.bot.send_audio(uid, fh)
                sent = True
                log.info("📨 Bot DM sent to %s", uid)

            except TelegramError as e:
                log.warning("Bot DM failed for %s: %s", uid, e)
            except Exception as e:
                log.warning("Bot DM error for %s: %s", uid, e)

        if not sent:
            log.warning("⚠️  All DM methods failed for %s", uid)

        await asyncio.sleep(0.6)

# ══════════════════════════════════════════════════════════
#  APP LIFECYCLE HOOKS
# ══════════════════════════════════════════════════════════

async def post_init(application: Application) -> None:
    """Called once when the application starts (inside the running event loop)."""
    os.makedirs(MEDIA_DIR, exist_ok=True)
    ub_ok = await start_userbot()
    if ub_ok:
        log.info("👤  Userbot: ACTIVE (sends as channel admin)")
    else:
        log.info("👤  Userbot: not configured — use /admin → Setup Userbot")

async def post_shutdown(application: Application) -> None:
    """Graceful cleanup on exit."""
    global userbot
    if userbot:
        try:
            await userbot.disconnect()
            log.info("Userbot disconnected.")
        except Exception:
            pass

# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

def main() -> None:
    if BOT_TOKEN in ("YOUR_BOT_TOKEN_HERE", "") or not BOT_TOKEN:
        print("❌  ERROR: Please set BOT_TOKEN at the top of the script.")
        return

    print("""
╔══════════════════════════════════════════════════════════════╗
║    🤖  CHANNEL JOIN REQUEST MANAGER BOT                     ║
║   ─────────────────────────────────────────────────────      ║
║   ✅  Starting up...                                         ║
║   📋  Use /admin to access the admin panel                   ║
║   🔐  Default Password: Void#123                             ║
╚══════════════════════════════════════════════════════════════╝
""")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # ── Register all handlers ─────────────────────────────
    app.add_handler(CommandHandler(
        "start", cmd_start,
        filters=filters.ChatType.PRIVATE,
    ))
    app.add_handler(CommandHandler(
        "admin", cmd_admin,
        filters=filters.ChatType.PRIVATE,
    ))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.PHOTO,
        on_photo,
    ))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.VOICE | filters.AUDIO),
        on_audio,
    ))
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
        on_text,
    ))
    app.add_handler(ChatJoinRequestHandler(on_join_request))

    log.info("📡 Bot polling started. Waiting for join requests…")

    # run_polling handles its own event loop — works on Pydroid3 & Linux alike
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
