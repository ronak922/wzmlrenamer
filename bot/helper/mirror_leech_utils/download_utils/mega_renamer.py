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
from collections import deque
from ....helper.telegram_helper.message_utils import *

# ─────────────────────────────
# Global Rename Tracker
# ─────────────────────────────
ACTIVE_RENAMES = set()  # Active user IDs
LAST_RENAMES = deque(maxlen=5)  # Stores tuples of (user_id, username, elapsed_time)

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

# ─────────────────────────────
# /rename — Safe & Stable Version
# ─────────────────────────────
async def rename_mega_command(client, message):
    try:
        user_id = message.from_user.id
        username = message.from_user.first_name or "Unknown"

        # Prevent double rename sessions for same user
        if user_id in ACTIVE_RENAMES:
            return await send_message(message, "⚠️ <b>ᴀ ʀᴇɴᴀᴍᴇ ᴊᴏʙ ɪꜱ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ ꜰᴏʀ ʏᴏᴜ.</b>")

        args = message.text.split(maxsplit=3)
        if len(args) < 3:
            return await send_message(
                message,
                "<b>⚙️ ᴜsᴀɢᴇ:\n/rename <email> <password>\n\n📘 ᴇxᴀᴍᴘʟᴇ:\n/rename test@gmail.com mypass</b>"
            )

        email, password = args[1], args[2]
        ACTIVE_RENAMES.add(user_id)

        rename_prefix = await database.get_user_prefix(user_id)
        rename_folders = await database.get_user_folder_state(user_id)
        swap_mode = await database.get_user_swap_state(user_id)

        msg = await send_message(message, "<b>🔐 ʟᴏɢɪɴɢ ɪɴᴛᴏ ᴍᴇɢᴀ...</b>")
        start_time = t.time()

        async_api = AsyncMega()
        async_api.api = api = MegaApi(None, None, None, f"MEGA_RENAMER_{user_id}")
        mega_listener = MegaAppListener(async_api.continue_event, None)
        api.addListener(mega_listener)

        loop = asyncio.get_event_loop()
        semaphore = asyncio.Semaphore(2)

        await async_api.login(email, password)
        await msg.edit_text("<b>✅ ʟᴏɢɪɴ sᴜᴄᴄᴇssꜰᴜʟ\n📂 ꜰᴇᴛᴄʜɪɴɢ ꜱᴛʀᴜᴄᴛᴜʀᴇ...</b>")
        root = api.getRootNode()

        async def safe_rename(item, new_name):
            """Throttle + offload rename to prevent overload"""
            async with semaphore:
                await asyncio.sleep(random.uniform(0.05, 0.15))
                return await sync_to_async(api.renameNode, item, new_name)

        async def traverse_and_rename(node, level=0, counter=[0]):
            children = api.getChildren(node)
            if not children or children.size() == 0:
                return []

            results = []
            for i in range(children.size()):
                item = children.get(i)
                name = item.getName()
                is_folder = item.isFolder()

                if rename_prefix and (not is_folder or rename_folders):
                    counter[0] += 1
                    if swap_mode:
                        new_name = re.sub(r"@\w+", rename_prefix, name)
                    else:
                        base, ext = os.path.splitext(name)
                        new_name = f"{rename_prefix}_{counter[0]}{ext}" if ext else f"{rename_prefix}_{counter[0]}"
                    try:
                        await safe_rename(item, new_name)
                    except Exception as e:
                        LOGGER.warning(f"❌ Rename failed for {name}: {e}")

                if is_folder:
                    await asyncio.sleep(0.05)
                    sub = await traverse_and_rename(item, level + 1, counter)
                    results.extend(sub)
                results.append(name)
            return results

        results = await traverse_and_rename(root)
        total = len(results)
        await async_api.logout()

        elapsed = round(t.time() - start_time, 2)
        LAST_RENAMES.appendleft((user_id, username, elapsed))
        ACTIVE_RENAMES.remove(user_id)

        await msg.edit_text(
            f"<b>✅ ʀᴇɴᴀᴍᴇᴅ {total} ɪᴛᴇᴍꜱ\n\n"
            f"🔤 ᴘʀᴇꜰɪx: <code>{rename_prefix or 'ɴᴏɴᴇ'}</code>\n"
            f"📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ: {'✅ ᴇɴᴀʙʟᴇᴅ' if rename_folders else '🚫 ᴅɪꜱᴀʙʟᴇᴅ'}\n"
            f"🔁 sᴡᴀᴘ ᴍᴏᴅᴇ: {'✅ ᴇɴᴀʙʟᴇᴅ' if swap_mode else '🚫 ᴅɪꜱᴀʙʟᴇᴅ'}\n"
            f"⏱️ {elapsed}s</b>"
        )

    except Exception as e:
        LOGGER.error(f"❌ rename_mega_command crashed: {e}", exc_info=True)
        if user_id in ACTIVE_RENAMES:
            ACTIVE_RENAMES.remove(user_id)
        await send_message(message, f"🚨 <b>ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:</b>\n<code>{e}</code>")

# ─────────────────────────────
# /status — Check rename status
# ─────────────────────────────
@TgClient.bot.on_message(filters.command("status"))
async def rename_status(_, message):
    # Active rename users
    if ACTIVE_RENAMES:
        active_list = "\n".join([f"• <code>{uid}</code>" for uid in ACTIVE_RENAMES])
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
# Register handlers
# ─────────────────────────────
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_folder, filters.regex(r"^toggle_folder_\d$")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_swap, filters.regex(r"^toggle_swap_\d$")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_refresh_settings, filters.regex(r"^refresh_settings$")))
