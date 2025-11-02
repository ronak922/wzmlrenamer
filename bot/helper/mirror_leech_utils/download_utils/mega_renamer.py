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
from ....helper.telegram_helper.message_utils import *
import gc
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


# ─────────────────────────────
# /rename — Rename files in Mega (premium-aware + failure count)
# ─────────────────────────────
async def rename_mega_command(client, message):
    try:
        args = message.text.split(maxsplit=3)
        if len(args) < 3:
            return await send_message(
                message,
                "<b>⚙️ ᴜsᴀɢᴇ:\n/rename &lt;email&gt; &lt;password&gt;\n\n📘 ᴇxᴀᴍᴘʟᴇ:\n/rename test@gmail.com mypass</b>"
            )

        email, password = args[1], args[2]
        user_id = message.from_user.id

        # ─── USER CONFIG ───
        rename_prefix = await database.get_user_prefix(user_id)
        rename_folders = await database.get_user_folder_state(user_id)
        swap_mode = await database.get_user_swap_state(user_id)
        is_premium = await database.is_user_premium(user_id)  # ✅ Check premium status

        msg = await send_message(message, "<b>🔐 ʟᴏɢɪɴɢ ɪɴᴛᴏ ᴍᴇɢᴀ...</b>")
        start_time = t.time()

        async_api = AsyncMega()
        async_api.api = api = MegaApi(None, None, None, "MEGA_RENAMER_BOT")
        mega_listener = MegaAppListener(async_api.continue_event, None)
        api.addListener(mega_listener)

        # ─── LOGIN ───
        try:
            await async_api.login(email, password)
            await msg.edit_text("<b>✅ ʟᴏɢɪɴ sᴜᴄᴄᴇssꜰᴜʟ\n📂 ꜰᴇᴛᴄʜɪɴɢ ꜱᴛʀᴜᴄᴛᴜʀᴇ...</b>")
        except Exception as e:
            err = str(e).lower()
            LOGGER.error(f"❌ ᴍᴇɢᴀ ʟᴏɢɪɴ ꜰᴀɪʟᴇᴅ ꜰᴏʀ {email}: {e}")
            try: await async_api.logout()
            except Exception: pass
            try: del async_api.api
            except Exception: pass
            gc.collect()

            if "credentials" in err or "eaccess" in err:
                return await msg.edit_text("❌ <b>ʟᴏɢɪɴ ꜰᴀɪʟᴇᴅ:</b> ɪɴᴠᴀʟɪᴅ ᴇᴍᴀɪʟ ᴏʀ ᴘᴀssᴡᴏʀᴅ.")
            elif "enoent" in err:
                return await msg.edit_text("⚠️ <b>ɴᴇᴛᴡᴏʀᴋ ᴇʀʀᴏʀ:</b> ᴍᴇɢᴀ ᴀᴄᴄᴏᴜɴᴛ ɴᴏᴛ ꜰᴏᴜɴᴅ.")
            elif "too many" in err or "limit" in err:
                return await msg.edit_text("🚫 <b>ᴛᴏᴏ ᴍᴀɴʏ ʟᴏɢɪɴ ᴀᴛᴛᴇᴍᴘᴛs.</b> ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.")
            else:
                return await msg.edit_text(f"❌ <b>ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ:</b>\n<code>{e}</code>")

        # ─── RENAME PROCESS ───
        root = api.getRootNode()
        limit = 999999999 if is_premium else 50  # ✅ Premium unlimited, free limited
        failed = 0

        async def traverse_and_rename(node, level=0, counter=[0]):
            nonlocal failed
            if counter[0] >= limit:
                return []

            children = api.getChildren(node)
            if not children or children.size() == 0:
                return []

            results = []
            for i in range(children.size()):
                if counter[0] >= limit:
                    break

                item = children.get(i)
                try:
                    name = item.getName()
                    is_folder = item.isFolder()
                except Exception:
                    continue

                icon = "📁" if is_folder else "📄"
                results.append(f"{'  ' * level}<b><blockquote expandable>{icon} {name}</blockquote></b>")

                if rename_prefix and (not is_folder or rename_folders):
                    counter[0] += 1
                    new_name = name
                    if swap_mode:
                        try:
                            new_name = re.sub(r"@\w+", rename_prefix, name)
                        except Exception:
                            new_name = f"{rename_prefix}_{counter[0]}"
                    else:
                        base, ext = os.path.splitext(name)
                        new_name = f"{rename_prefix}_{counter[0]}{ext}" if ext else f"{rename_prefix}_{counter[0]}"

                    try:
                        await sync_to_async(api.renameNode, item, new_name)
                    except Exception as e:
                        failed += 1
                        LOGGER.error(f"❌ Rename failed for {name}: {e}")

                if is_folder:
                    sub_results = await traverse_and_rename(item, level + 1, counter)
                    results.extend(sub_results)

            return results

        results = await traverse_and_rename(root)
        total = len(results)
        time_taken = round(t.time() - start_time, 2)

        # ─── RESULT ───
        if not results:
            await msg.edit_text("<b>⚠️ ɴᴏ ꜰɪʟᴇꜱ ᴏʀ ꜰᴏʟᴅᴇʀꜱ ꜰᴏᴜɴᴅ.</b>")
        else:
            limit_text = "∞ (ᴘʀᴇᴍɪᴜᴍ)" if is_premium else "50 (ꜰʀᴇᴇ ʟɪᴍɪᴛ)"
            await msg.edit_text(
                f"<b>✅ ʀᴇɴᴀᴍᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ\n\n"
                # f"📦 ᴜꜱᴇʀ ᴛʏᴘᴇ:</b> {'<code>Premium 🟢</code>' if is_premium else '<code>Free 🔴</code>'}\n"
                f"<b>🔢 ᴛᴏᴛᴀʟ ɪᴛᴇᴍꜱ:</b> <code>{min(total, limit)}</code>\n"
                f"<b>⚠️ ꜰᴀɪʟᴇᴅ ɪᴛᴇᴍꜱ:</b> <code>{failed}</code>\n"
                f"<b>🔤 ᴘʀᴇꜰɪx:</b> <code>{rename_prefix or 'ɴᴏɴᴇ'}</code>\n"
                f"<b>📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ:</b> {'✅ ᴇɴᴀʙʟᴇᴅ' if rename_folders else '🚫 ᴅɪsᴀʙʟᴇᴅ'}\n"
                f"<b>🔁 sᴡᴀᴘ ᴍᴏᴅᴇ:</b> {'✅ ᴇɴᴀʙʟᴇᴅ' if swap_mode else '🚫 ᴅɪsᴀʙʟᴇᴅ'}\n"
                # f"<b>📈 ʟɪᴍɪᴛ:</b> <code>{limit_text}</code>\n"
                f"<b>⏱️ ᴛɪᴍᴇ:</b> <code>{time_taken}s</code></b>"
            )

        # ─── CLEANUP ───
        try: await async_api.logout()
        except Exception: pass
        await asyncio.sleep(0.3)
        try: api.removeListener(mega_listener)
        except Exception: pass
        try: del async_api, api
        except Exception: pass
        gc.collect()

    except Exception as e:
        LOGGER.error(f"❌ ᴍᴇɢᴀ ʀᴇɴᴀᴍᴇ ᴇʀʀᴏʀ: {e}", exc_info=True)
        await send_message(message, f"🚨 <b>ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ:</b>\n<code>{e}</code>")


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
# Register handlers
# ─────────────────────────────
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_folder, filters.regex(r"^toggle_folder_\d$")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_swap, filters.regex(r"^toggle_swap_\d$")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_refresh_settings, filters.regex(r"^refresh_settings$")))
