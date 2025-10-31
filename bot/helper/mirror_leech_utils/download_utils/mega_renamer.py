from mega import MegaApi
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from pyrogram.handlers import CallbackQueryHandler
from .... import LOGGER
from ...listeners.mega_listener import AsyncMega, MegaAppListener
from ...telegram_helper.message_utils import send_message, edit_message
from ...ext_utils.bot_utils import sync_to_async
from ....helper.ext_utils.db_handler import database
from ....helper.telegram_helper.button_build import ButtonMaker
from ....core.tg_client import TgClient
import os, time, re, random, asyncio
import time as t
from ....helper.telegram_helper.filters import CustomFilters
# from ..modules import *
from collections import deque
from ....helper.telegram_helper.message_utils import *

# ─────────────────────────────
# Global Rename Tracker
# ─────────────────────────────
# switched to dict to store control events and progress per user
ACTIVE_RENAMES = {}  # { user_id: {"cancel": Event, "pause": Event, "count": int, "total": int, "msg_id": int, "chat_id": int } }
LAST_RENAMES = deque(maxlen=5)  # Stores tuples of (user_id, username, elapsed_time)

# small helper: visual progress bar using 5 blocks (▰ = filled, ▱ = empty)
def _progress_bar(done, total, blocks=5):
    try:
        pct = (done / total) if total else 0
    except Exception:
        pct = 0
    filled = int(pct * blocks)
    bar = "▰" * filled + "▱" * (blocks - filled)
    percent_text = f"{pct*100:5.1f}%"
    return bar, percent_text

# ─────────────────────────────
# /prefix — Save user prefix
# ─────────────────────────────
async def prefix_command(_, message):
    userid = message.from_user.id
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        return await send_message(
            message,
            "<b>⚙️ ᴜsᴀɢᴇ:\n/prefix <ᴘʀᴇꜰɪx>\n\n📘 ᴇxᴀᴍᴘʟᴇ:\n/prefix @BhookiBhabhi</b>"
        )

    prefix = args[1].strip()
    await database.set_user_prefix(userid, prefix)
    await send_message(message, f"<b>✅ ᴘʀᴇꜰɪx sᴇᴛ ᴛᴏ: {prefix}</b>")

async def rename_mega_command(client, message):
    try:
        args = message.text.split(maxsplit=3)
        if len(args) < 3:
            return await send_message(
                message,
                "<b>⚙️ ᴜsᴀɢᴇ:\n/rename <email> <password>\n\n📘 ᴇxᴀᴍᴘʟᴇ:\n/rename test@gmail.com mypass</b>"
            )

        email, password = args[1], args[2]
        user_id = message.from_user.id

        rename_prefix = await database.get_user_prefix(user_id)
        rename_folders = await database.get_user_folder_state(user_id)
        swap_mode = await database.get_user_swap_state(user_id)

        msg = await send_message(message, "<b>🔐 ʟᴏɢɪɴɢ ɪɴᴛᴏ ᴍᴇɢᴀ...</b>")
        start_time = t.time()

        async_api = AsyncMega()
        async_api.api = api = MegaApi(None, None, None, f"MEGA_RENAMER_{user_id}")
        mega_listener = MegaAppListener(async_api.continue_event, None)
        api.addListener(mega_listener)

        # Thread-safe Mega operations
        loop = asyncio.get_event_loop()
        semaphore = asyncio.Semaphore(2)

        await async_api.login(email, password)
        await msg.edit_text("<b>✅ ʟᴏɢɪɴ sᴜᴄᴄᴇssꜰᴜʟ\n📂 ꜰᴇᴛᴄʜɪɴɢ ꜱᴛʀᴜᴄᴛᴜʀᴇ...</b>")
        root = api.getRootNode()

        # Helper: progress bar generator
        def progress_bar(done, total, blocks=10):
            if total == 0:
                return "▱" * blocks, "0%"
            pct = done / total
            filled = int(pct * blocks)
            bar = "▰" * filled + "▱" * (blocks - filled)
            return bar, f"{pct*100:5.1f}%"

        total_items = 0
        renamed = 0
        last_update = t.time()

        async def safe_rename(item, new_name):
            async with semaphore:
                await asyncio.sleep(random.uniform(0.05, 0.15))
                return await sync_to_async(api.renameNode, item, new_name)

        async def traverse_and_rename(node, counter=[0]):
            nonlocal total_items, renamed, last_update

            children = api.getChildren(node)
            if not children or children.size() == 0:
                return

            total_items += children.size()

            for i in range(children.size()):
                item = children.get(i)
                name = item.getName()
                is_folder = item.isFolder()

                if rename_prefix and (not is_folder or rename_folders):
                    counter[0] += 1
                    renamed += 1
                    if swap_mode:
                        new_name = re.sub(r"@\w+", rename_prefix, name)
                    else:
                        base, ext = os.path.splitext(name)
                        new_name = f"{rename_prefix}_{counter[0]}{ext}" if ext else f"{rename_prefix}_{counter[0]}"

                    try:
                        await safe_rename(item, new_name)
                    except Exception as e:
                        LOGGER.warning(f"❌ Rename failed for {name}: {e}")

                # update progress every 3s
                if t.time() - last_update >= 3:
                    last_update = t.time()
                    bar, pct = progress_bar(renamed, total_items)
                    elapsed = round(t.time() - start_time, 1)
                    speed = renamed / elapsed if elapsed else 0
                    await edit_message(
                        msg,
                        (
                            f"<b>🔁 ʀᴇɴᴀᴍɪɴɢ ɪɴ ᴘʀᴏɢʀᴇss\n\n"
                            f"{bar} {pct}\n"
                            f"📦 {renamed}/{total_items} ɪᴛᴇᴍꜱ\n"
                            f"⏱️ {elapsed}s — ⚙️ {speed:.2f} files/s\n\n"
                            f"👤 <b>ᴘʀᴇꜰɪx:</b> <code>{rename_prefix or 'ɴᴏɴᴇ'}</code></b>"
                        ),
                    )

                if is_folder:
                    await traverse_and_rename(item, counter)

        await traverse_and_rename(root)
        await async_api.logout()

        elapsed = round(t.time() - start_time, 2)
        bar, pct = progress_bar(renamed, total_items)
        await msg.edit_text(
            f"<b>✅ ʀᴇɴᴀᴍᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n\n"
            f"<blockquote>{bar} {pct}\n📦 {renamed}/{total_items} ɪᴛᴇᴍꜱ</blockquote>\n\n"
            f"🔤 ᴘʀᴇꜰɪx: <code>{rename_prefix or 'ɴᴏɴᴇ'}</code>\n"
            f"📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ: {'✅ ᴇɴᴀʙʟᴇᴅ' if rename_folders else '🚫 ᴅɪꜱᴀʙʟᴇᴅ'}\n"
            f"🔁 sᴡᴀᴘ ᴍᴏᴅᴇ: {'✅ ᴇɴᴀʙʟᴇᴅ' if swap_mode else '🚫 ᴅɪꜱᴀʙʟᴇᴅ'}\n"
            f"⏱️ {elapsed}s — ⚙️ {renamed/elapsed:.2f} files/s"
        )

    except Exception as e:
        LOGGER.error(f"❌ rename_mega_command crashed: {e}", exc_info=True)
        await send_message(message, f"🚨 <b>ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:</b>\n<code>{e}</code>")


# ─────────────────────────────
# /status — Check rename status
# ─────────────────────────────
@TgClient.bot.on_message(filters.command("status")& CustomFilters.authorized,)
async def rename_status(_, message):
    # Active rename users
    if ACTIVE_RENAMES:
        active_list = "\n".join([f"• <code>{uid}</code>" for uid in ACTIVE_RENAMES.keys()])
        active_text = f"🟢 <b>ᴀᴄᴛɪᴠᴇ ʀᴇɴᴀᴍᴇ ᴜsᴇʀꜱ:</b>\n{active_list}"
    else:
        active_text = "⚪ <b>ɴᴏ ᴀᴄᴛɪᴠᴇ ʀᴇɴᴀᴍᴇ ᴊᴏʙꜱ</b>"

    # Recent users (from memory)
    if LAST_RENAMES:
        recent_lines = []
        for uid, name, duration in list(LAST_RENAMES):
            recent_lines.append(f"• <b>{name}</b> (<code>{uid}</code>) — ⏱️ {duration}s")
        recent_text = "\n".join(recent_lines)
    else:
        recent_text = "❌ ɴᴏ ʀᴇᴄᴇɴᴛ ʀᴇɴᴀᴍᴇ ᴊᴏʙꜱ"

    await send_message(
        message,
        f"<b>📊 ʀᴇɴᴀᴍᴇ ꜱᴛᴀᴛᴜꜱ</b>\n\n"
        f"{active_text}\n\n"
        f"🕓 <b>ʟᴀꜱᴛ 5 ᴜꜱᴇʀꜱ:</b>\n{recent_text}"
    )

# ─────────────────────────────
# /settings — Manage user settings
# ─────────────────────────────
async def settings_command(client, message):
    user_id = message.from_user.id
    await send_settings_view(client, message, user_id)

# ─────────────────────────────
# Helper — builds and sends settings view
# ─────────────────────────────
async def send_settings_view(client, message, user_id, edit=False):
    prefix = await database.get_user_prefix(user_id)
    rename_folders = await database.get_user_folder_state(user_id)
    swap_mode = await database.get_user_swap_state(user_id)

    prefix_text = prefix or "❌ ɴᴏ ᴘʀᴇꜰɪx sᴇᴛ"
    folder_state = "✅ ᴇɴᴀʙʟᴇᴅ" if rename_folders else "🚫 ᴅɪsᴀʙʟᴇᴅ"
    swap_state = "✅ ᴇɴᴀʙʟᴇᴅ" if swap_mode else "🚫 ᴅɪsᴀʙʟᴇᴅ"

    text = (
        f"<b>⚙️ ᴜꜱᴇʀ ꜱᴇᴛᴛɪɴɢꜱ\n\n"
        f"<blockquote>🔤 ᴘʀᴇꜰɪx: {prefix_text}\n"
        f"📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ: {folder_state}\n"
        f"🔁 ɴᴀᴍᴇ ꜱᴡᴀᴘ: {swap_state}</blockquote>\n\n"
        f"ᴛᴀᴘ ᴛᴏ ᴛᴏɢɢʟᴇ ᴏᴘᴛɪᴏɴꜱ ↓</b>"
    )

    buttons = ButtonMaker()
    buttons.data_button("📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ", f"toggle_folder_{int(not rename_folders)}")
    buttons.data_button("🔁 ɴᴀᴍᴇ ꜱᴡᴀᴘ", f"toggle_swap_{int(not swap_mode)}")
    buttons.data_button("🔄 ʀᴇꜰʀᴇꜱʜ", "refresh_settings")

    markup = buttons.build_menu(1)
    photo_url = "https://i.ibb.co/9kCPFWrb/image.jpg"

    if edit:
        await message.edit_media(
            InputMediaPhoto(photo_url, caption=text),
            reply_markup=markup
        )
    else:
        await client.send_photo(
            chat_id=message.chat.id,
            photo=photo_url,
            caption=text,
            reply_markup=markup,
            message_effect_id=5104841245755180586
        )
    await delete_message(message)

# ─────────────────────────────
# Callback: Toggle folder rename
# ─────────────────────────────
async def cb_toggle_folder(client, q):
    user_id = q.from_user.id
    new_state = bool(int(q.data.split("_")[-1]))
    await database.set_user_folder_state(user_id, new_state)
    await q.answer(f"📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ {'✅ ᴇɴᴀʙʟᴇᴅ' if new_state else '🚫 ᴅɪꜱᴀʙʟᴇᴅ'}", show_alert=True)
    await send_settings_view(client, q.message, user_id, edit=True)

# ─────────────────────────────
# Callback: Toggle swap mode
# ─────────────────────────────
async def cb_toggle_swap(client, q):
    user_id = q.from_user.id
    new_state = bool(int(q.data.split("_")[-1]))
    await database.set_user_swap_state(user_id, new_state)
    await q.answer(f"🔁 ꜱᴡᴀᴘ ᴍᴏᴅᴇ {'✅ ᴇɴᴀʙʟᴇᴅ' if new_state else '🚫 ᴅɪꜱᴀʙʟᴇᴅ'}", show_alert=True)
    await send_settings_view(client, q.message, user_id, edit=True)

# ─────────────────────────────
# Callback: Refresh settings
# ─────────────────────────────
async def cb_refresh_settings(client, q):
    await edit_message(q.message, "<b>🔄 ʀᴇꜰʀᴇꜱʜɪɴɢ ᴜsᴇʀ ꜱᴇᴛᴛɪɴɢꜱ...</b>")
    await q.answer("🔄 ʀᴇꜰʀᴇꜱʜɪɴɢ...", show_alert=False)
    await send_settings_view(client, q.message, q.from_user.id, edit=True)

# ─────────────────────────────
# Inline Pause / Resume / Stop callbacks
# ─────────────────────────────
async def cb_pause_resume_rename(client, q):
    # data like: pause_resume_rename_<user_id>
    parts = q.data.split("_")
    try:
        uid = int(parts[-1])
    except Exception:
        return await q.answer("⚠️ ɪɴᴠᴀʟɪᴅ ʀᴇQ.")

    job = ACTIVE_RENAMES.get(uid)
    if not job:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴊᴏʙ.", show_alert=True)

    pause_event = job["pause"]
    # toggle pause: if set -> clear (pause); if clear -> set (resume)
    if pause_event.is_set():
        # currently running -> pause it
        pause_event.clear()
        # update message to show paused state and show Resume button
        try:
            chat = job.get("msg_chat")
            mid = job.get("msg_id")
            resume_buttons = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("▶️ ʀᴇsᴜᴍᴇ", callback_data=f"pause_resume_rename_{uid}"),
                    InlineKeyboardButton("⏹ sᴛᴏᴘ", callback_data=f"stop_rename_{uid}")
                ]]
            )
            await client.edit_message_text(chat_id=chat, message_id=mid,
                                           text="<b>⏸ ᴘᴀᴜsᴇᴅ — ᴛᴀᴘ ᴛᴏ ʀᴇsᴜᴍᴇ</b>",
                                           reply_markup=resume_buttons)
        except Exception:
            pass
        await q.answer("⏸ ᴘᴀᴜsᴇᴅ", show_alert=False)
    else:
        # currently paused -> resume
        pause_event.set()
        try:
            chat = job.get("msg_chat")
            mid = job.get("msg_id")
            buttons = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("⏸ ᴘᴀᴜsᴇ", callback_data=f"pause_resume_rename_{uid}"),
                    InlineKeyboardButton("⏹ sᴛᴏᴘ", callback_data=f"stop_rename_{uid}")
                ]]
            )
            # show quick resume notice then restore progress by forcing a small update in rename loop
            await client.edit_message_text(chat_id=chat, message_id=mid,
                                           text="<b>▶️ ʀᴇsᴜᴍɪɴɢ ʀᴇɴᴀᴍᴇ...</b>",
                                           reply_markup=buttons)
        except Exception:
            pass
        await q.answer("▶️ ʀᴇsᴜᴍᴇᴅ", show_alert=False)

async def cb_stop_rename(client, q):
    # data like: stop_rename_<user_id>
    parts = q.data.split("_")
    try:
        uid = int(parts[-1])
    except Exception:
        return await q.answer("⚠️ ɪɴᴠᴀʟɪᴅ ʀᴇQ.")

    job = ACTIVE_RENAMES.get(uid)
    if not job:
        return await q.answer("⚠️ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴊᴏʙ.", show_alert=True)

    # signal cancel; the running loop checks this and will finish shortly
    job["cancel"].set()
    # also ensure pause is released so it can stop if paused
    job["pause"].set()

    # edit message to show stopping state
    try:
        chat = job.get("msg_chat")
        mid = job.get("msg_id")
        await client.edit_message_text(chat_id=chat, message_id=mid,
                                       text="<b>⏹ sᴛᴏᴘᴘɪɴɢ — ᴄʟᴇᴀɴɪɴɢ ᴜᴘ...</b>")
    except Exception:
        pass

    await q.answer("⏹  sᴛᴏᴘᴘɪɴɢ ʀᴇɴᴀᴍᴇ...", show_alert=False)

# ─────────────────────────────
# Register handlers
# ─────────────────────────────
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_folder, filters.regex(r"^toggle_folder_\d$")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_swap, filters.regex(r"^toggle_swap_\d$")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_refresh_settings, filters.regex(r"^refresh_settings$")))

# pause/resume and stop handlers for rename UI
TgClient.bot.add_handler(CallbackQueryHandler(cb_pause_resume_rename, filters.regex(r"^pause_resume_rename_\d+$")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_stop_rename, filters.regex(r"^stop_rename_\d+$")))
