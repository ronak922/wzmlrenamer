from mega import MegaApi
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from pyrogram.handlers import CallbackQueryHandler
from .... import LOGGER
from ...listeners.mega_listener import MegaAppListener
from ...telegram_helper.message_utils import send_message, edit_message
from ...ext_utils.bot_utils import sync_to_async
from ....helper.ext_utils.db_handler import database
from ....helper.telegram_helper.button_build import ButtonMaker
from ....core.tg_client import TgClient
import os, time, re, random, asyncio
import time as t
from ....helper.telegram_helper.message_utils import *
import gc
from datetime import datetime, timedelta
from config import OWNER_ID

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
                "<b>⚙️ ᴜsᴀɢᴇ:</b>\n/rename &lt;email&gt; &lt;password&gt;"
            )

        email, password = args[1], args[2]
        user_id = message.from_user.id

        rename_prefix = await database.get_user_prefix(user_id)
        rename_folders = await database.get_user_folder_state(user_id)
        swap_mode = await database.get_user_swap_state(user_id)
        is_premium = await database.is_user_premium(user_id)

        msg = await send_message(message, "<b>🔐 ʟᴏɢɪɴɢ ɪɴᴛᴏ ᴍᴇɢᴀ...</b>")
        start_time = t.time()

        # ─── INIT MEGA ───
        api = MegaApi(None, None, None, "MEGA_RENAMER_BOT")
        continue_event = asyncio.Event()
        mega_listener = MegaAppListener(continue_event, None)
        api.addListener(mega_listener)

        # ─── LOGIN ───
        continue_event.clear()
        await sync_to_async(api.login, email, password)
        await continue_event.wait()

        if mega_listener.error:
            raise Exception(mega_listener.error)

        continue_event.clear()
        await sync_to_async(api.fetchNodes)
        await continue_event.wait()

        root = api.getRootNode()
        limit = 999999999 if is_premium else 50
        failed = 0
        renamed = 0

        async def rename_node_safe(node, new_name):
            continue_event.clear()
            await sync_to_async(api.renameNode, node, new_name)
            await continue_event.wait()

            if mega_listener.error:
                raise Exception(mega_listener.error)

        async def traverse(node):
            nonlocal failed, renamed
            children = api.getChildren(node)
            if not children:
                return

            for i in range(children.size()):
                if renamed >= limit:
                    return

                item = children.get(i)
                try:
                    name = item.getName()
                    is_folder = item.isFolder()
                except Exception:
                    continue

                if rename_prefix and (not is_folder or rename_folders):
                    try:
                        renamed += 1
                        if swap_mode:
                            new_name = re.sub(r"@\w+", rename_prefix, name)
                        else:
                            base, ext = os.path.splitext(name)
                            new_name = f"{rename_prefix}_{renamed}{ext}"

                        await rename_node_safe(item, new_name)
                        await asyncio.sleep(0.4)  # MEGA safety
                    except Exception as e:
                        failed += 1
                        LOGGER.error(f"Rename failed: {name} → {e}")

                if is_folder:
                    await traverse(item)

        await traverse(root)

        time_taken = round(t.time() - start_time, 2)

        await msg.edit_text(
            f"<b>✅ ʀᴇɴᴀᴍᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n\n"
            f"🔢 ᴛᴏᴛᴀʟ: <code>{renamed}</code>\n"
            f"⚠️ ꜰᴀɪʟᴇᴅ: <code>{failed}</code>\n"
            f"⏱️ ᴛɪᴍᴇ: <code>{time_taken}s</code>"
        )

        await database.increment_user_rename_count(user_id, renamed)

        # ─── CLEANUP ───
        continue_event.clear()
        await sync_to_async(api.logout)
        api.removeListener(mega_listener)
        del api, mega_listener
        gc.collect()

    except Exception as e:
        LOGGER.error("MEGA RENAME ERROR", exc_info=True)
        await send_message(message, f"❌ <b>ᴇʀʀᴏʀ:</b>\n<code>{e}</code>")



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
    await q.answer(f"📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ {'✅ ᴇɴᴀʙʟᴇᴅ' if new_state else '🚫 ᴅɪsᴀʙʟᴇᴅ'}", show_alert=True)
    await send_settings_view(client, q.message, user_id, edit=True)


# ─────────────────────────────
# Callback: Toggle swap mode
# ─────────────────────────────
async def cb_toggle_swap(client, q):
    user_id = q.from_user.id
    new_state = bool(int(q.data.split("_")[-1]))
    await database.set_user_swap_state(user_id, new_state)
    await q.answer(f"🔁 ꜱᴡᴀᴘ ᴍᴏᴅᴇ {'✅ ᴇɴᴀʙʟᴇᴅ' if new_state else '🚫 ᴅɪsᴀʙʟᴇᴅ'}", show_alert=True)
    await send_settings_view(client, q.message, user_id, edit=True)


# ─────────────────────────────
# Callback: Refresh settings
# ─────────────────────────────
async def cb_refresh_settings(client, q):
    await edit_message(q.message, "<b>🔄 ʀᴇꜰʀᴇꜱʜɪɴɢ ᴜsᴇʀ ꜱᴇᴛᴛɪɴɢꜱ...</b>")
    await q.answer("🔄 ʀᴇꜰʀᴇꜱʜɪɴɢ...", show_alert=False)
    await send_settings_view(client, q.message, q.from_user.id, edit=True)

# ─────────────────────────────
# /addpaid — Grant premium access for days
# ─────────────────────────────
# @Client.on_message(filters.command("addpaid"))
async def addpaid_command(_, message):
    if message.from_user.id != OWNER_ID:
        return await send_message(message, "🚫 <b>ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ.</b>")

    args = message.text.split(maxsplit=3)
    if len(args) < 2:
        return await send_message(
            message,
            "<b>⚙️ ᴜsᴀɢᴇ:</b>\n"
            "/addpaid <user_id> [days|0]\n\n"
            "<b>📘 ᴇxᴀᴍᴘʟᴇs:</b>\n"
            "/addpaid 12345 30 → 30 ᴅᴀʏꜱ\n"
            "/addpaid 12345 0 → ʀᴇᴍᴏᴠᴇ ᴘʀᴇᴍɪᴜᴍ"
        )

    try:
        user_id = int(args[1])
        days = int(args[2]) if len(args) > 2 else 0

        if days <= 0:
            await database.remove_user_premium(user_id)
            msg = f"❌ ᴜsᴇʀ <code>{user_id}</code> ᴘʀᴇᴍɪᴜᴍ ʀᴇᴠᴏᴋᴇᴅ"
        else:
            await database.set_user_premium(user_id, days)
            msg = f"💎 ᴜsᴇʀ <code>{user_id}</code> ᴘʀᴇᴍɪᴜᴍ ᴀᴅᴅᴇᴅ ꜰᴏʀ {days} ᴅᴀʏꜱ"

        await send_message(message, msg)

    except Exception as e:
        await send_message(message, f"❌ ᴇʀʀᴏʀ:\n<code>{e}</code>")

# ─────────────────────────────
# /status — Show user rename stats
# ─────────────────────────────
async def status_command(client, message):
    try:
        args = message.text.split(maxsplit=1)
        sender_id = message.from_user.id

        # ─── DETERMINE TARGET USER ───
        if len(args) > 1:
            # Only OWNER or ADMINS can view others' stats
            if sender_id != OWNER_ID:
                return await message.reply_text("<b>❌ ᴀᴅᴍɪɴ ᴏɴʟʏ..!</b>")

            # Try to parse ID or username
            try:
                target = args[1].strip()
                if target.startswith("@"):
                    user = await client.get_users(target)
                    user_id = user.id
                else:
                    user_id = int(target)
            except Exception:
                return await message.reply_text("⚠️ Invalid user ID or username.")
        else:
            user_id = sender_id  # Default: self

        # ─── FETCH USER INFO ───
        is_premium = await database.is_user_premium(user_id)
        premium_text = "💎 <b>ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀ</b>" if is_premium else "🆓 <b>ꜰʀᴇᴇ ᴜsᴇʀ</b>"
        rename_count = await database.get_user_rename_count(user_id)

        expiry_info = ""
        if is_premium:
            doc = await database.db.premium.find_one({"_id": user_id})
            if doc and doc.get("expiry"):
                expiry_dt = datetime.utcfromtimestamp(doc["expiry"])
                expiry_info = f"\n⏳ ᴇxᴘɪʀᴇs ᴏɴ: <b>{expiry_dt:%d-%b-%Y %H:%M UTC}</b>"

        # ─── MESSAGE FORMAT ───
        text = (
            f"👤 <b>ᴜꜱᴇʀ ɪᴅ:</b> <code>{user_id}</code>\n"
            f"{premium_text}{expiry_info}\n\n"
            f"📦 <b>ꜰɪʟᴇꜱ ʀᴇɴᴀᴍᴇᴅ:</b> <code>{rename_count}</code>"
        )

        await message.reply_text(text, quote=True)

    except Exception as e:
        await message.reply_text(f"❌ ᴇʀʀᴏʀ:\n<code>{e}</code>")



# ─────────────────────────────
# Register handlers
# ─────────────────────────────
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_folder, filters.regex(r"^toggle_folder_\d$")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_swap, filters.regex(r"^toggle_swap_\d$")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_refresh_settings, filters.regex(r"^refresh_settings$")))
