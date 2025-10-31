from mega import MegaApi
from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler
from .... import LOGGER
from ...listeners.mega_listener import AsyncMega, MegaAppListener
from ...telegram_helper.message_utils import send_message, edit_message
from ...ext_utils.bot_utils import sync_to_async
from ....helper.ext_utils.db_handler import database
from ....helper.telegram_helper.button_build import ButtonMaker
import os, time, re
from ....core.tg_client import TgClient
from pyrogram.filters import regex

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
# /rename — Rename files in Mega
# ─────────────────────────────
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

        msg = await send_message(message, "<b>🔐 ʟᴏɢɢɪɴɢ ɪɴᴛᴏ ᴍᴇɢᴀ...</b>")

        start_time = time.time()
        async_api = AsyncMega()
        async_api.api = api = MegaApi(None, None, None, "MEGA_RENAMER_BOT")
        mega_listener = MegaAppListener(async_api.continue_event, None)
        api.addListener(mega_listener)

        try:
            await async_api.login(email, password)
            await msg.edit_text("<b>✅ ʟᴏɢɪɴ sᴜᴄᴄᴇssꜰᴜʟ\n📂 ꜰᴇᴛᴄʜɪɴɢ ꜱᴛʀᴜᴄᴛᴜʀᴇ...</b>")
        except Exception as e:
            return await msg.edit_text(f"❌ ʟᴏɢɪɴ ꜰᴀɪʟᴇᴅ:\n{e}")

        root = api.getRootNode()

        async def traverse_and_rename(node, level=0, counter=[0]):
            children = api.getChildren(node)
            if not children or children.size() == 0:
                return []

            results = []
            for i in range(children.size()):
                item = children.get(i)
                name = item.getName()
                is_folder = item.isFolder()
                icon = "📁" if is_folder else "📄"
                results.append(f"{'  ' * level}<blockquote expandable>{icon} {name}</blockquote>")

                # ─── Rename logic ───
                if rename_prefix and (not is_folder or rename_folders):
                    counter[0] += 1
                    new_name = name

                    if swap_mode:
                        # 🔁 Swap @username in name
                        new_name = re.sub(r"@\w+", rename_prefix, name)
                    else:
                        base, ext = os.path.splitext(name)
                        new_name = f"{rename_prefix}_{counter[0]}{ext}" if ext else f"{rename_prefix}_{counter[0]}"

                    try:
                        await sync_to_async(api.renameNode, item, new_name)
                        LOGGER.info(f"Renamed: {name} → {new_name}")
                    except Exception as e:
                        LOGGER.error(f"❌ Rename failed for {name}: {e}")

                if is_folder:
                    sub_results = await traverse_and_rename(item, level + 1, counter)
                    results.extend(sub_results)

            return results

        results = await traverse_and_rename(root)
        total = len(results)
        time_taken = round(time.time() - start_time, 2)

        if not results:
            await msg.edit_text("<b>⚠️ ɴᴏ ꜰɪʟᴇꜱ ᴏʀ ꜰᴏʟᴅᴇʀꜱ ꜰᴏᴜɴᴅ.</b>")
        else:
            await msg.edit_text(
                f"<b>✅ ʀᴇɴᴀᴍᴇᴅ {total} ɪᴛᴇᴍꜱ\n"
                f"🔤 ᴘʀᴇꜰɪx: {rename_prefix or 'None'}\n"
                f"📂 ꜰᴏʟᴅᴇʀꜱ: {'✅' if rename_folders else '🚫'}\n"
                f"🔁 sᴡᴀᴘ ᴍᴏᴅᴇ: {'✅' if swap_mode else '🚫'}\n"
                f"⏱️ {time_taken}s</b>"
            )

        await async_api.logout()

    except Exception as e:
        LOGGER.error(f"Rename Mega error: {e}")
        await send_message(message, f"❌ ᴇʀʀᴏʀ: {e}")

# ─────────────────────────────
# /settings — Manage settings
# ─────────────────────────────
async def settings_command(_, message):
    user_id = message.from_user.id
    prefix = await database.get_user_prefix(user_id) or "None set"
    rename_folders = await database.get_user_folder_state(user_id)
    swap_mode = await database.get_user_swap_state(user_id)

    prefix_text = prefix if prefix else "❌ ɴᴏ ᴘʀᴇꜰɪx sᴇᴛ"
    folder_state = "✅ ᴇɴᴀʙʟᴇᴅ" if rename_folders else "🚫 ᴅɪsᴀʙʟᴇᴅ"
    swap_state = "✅ ᴇɴᴀʙʟᴇᴅ" if swap_mode else "🚫 ᴅɪsᴀʙʟᴇᴅ"

    text = (
        f"<b>⚙️ ᴜꜱᴇʀ ꜱᴇᴛᴛɪɴɢꜱ\n\n"
        f"🔤 ᴘʀᴇꜰɪx: {prefix_text}\n"
        f"📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ: {folder_state}\n"
        f"🔁 ɴᴀᴍᴇ ꜱᴡᴀᴘ: {swap_state}\n\n"
        f"ᴛᴀᴘ ᴛᴏ ᴛᴏɢɢʟᴇ ᴏᴘᴛɪᴏɴꜱ ↓</b>"
    )

    buttons = ButtonMaker()
    buttons.data_button("📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ", f"toggle_folder_{int(not rename_folders)}")
    buttons.data_button("🔁 ɴᴀᴍᴇ ꜱᴡᴀᴘ", f"toggle_swap_{int(not swap_mode)}")
    buttons.data_button("🔄 ʀᴇꜰʀᴇꜱʜ", "refresh_settings")

    reply_markup = buttons.build_menu(1)
    await send_message(message, text, buttons=reply_markup)

# ─────────────────────────────
# 🔧 Helper: refresh settings message
# ─────────────────────────────
async def refresh_settings_view(q):
    user_id = q.from_user.id
    prefix = await database.get_user_prefix(user_id)
    rename_folders = await database.get_user_folder_state(user_id)
    swap_mode = await database.get_user_swap_state(user_id)

    prefix_text = prefix or "❌ ɴᴏ ᴘʀᴇꜰɪx sᴇᴛ"
    folder_state = "✅ ᴇɴᴀʙʟᴇᴅ" if rename_folders else "🚫 ᴅɪsᴀʙʟᴇᴅ"
    swap_state = "✅ ᴇɴᴀʙʟᴇᴅ" if swap_mode else "🚫 ᴅɪsᴀʙʟᴇᴅ"

    text = (
        f"<b>⚙️ ᴜꜱᴇʀ ꜱᴇᴛᴛɪɴɢꜱ\n\n"
        f"🔤 ᴘʀᴇꜰɪx: {prefix_text}\n"
        f"📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ: {folder_state}\n"
        f"🔁 ɴᴀᴍᴇ ꜱᴡᴀᴘ: {swap_state}\n\n"
        f"ᴛᴀᴘ ᴛᴏ ᴛᴏɢɢʟᴇ ᴏᴘᴛɪᴏɴꜱ ↓</b>"
    )

    buttons = ButtonMaker()
    buttons.data_button("📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ", f"toggle_folder_{int(not rename_folders)}")
    buttons.data_button("🔁 ɴᴀᴍᴇ ꜱᴡᴀᴘ", f"toggle_swap_{int(not swap_mode)}")
    buttons.data_button("🔄 ʀᴇꜰʀᴇꜱʜ", "refresh_settings")

    reply_markup = buttons.build_menu(1)
    await edit_message(q.message, text, buttons=reply_markup)

# ─────────────────────────────
# 📂 Toggle folder rename
# ─────────────────────────────
async def cb_toggle_folder(client, callback_query):
    try:
        user_id = callback_query.from_user.id
        new_state = bool(int(callback_query.data.split("_")[-1]))
        await database.set_user_folder_state(user_id, new_state)
        await callback_query.answer(
            f"📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ {'ᴇɴᴀʙʟᴇᴅ' if new_state else 'ᴅɪꜱᴀʙʟᴇᴅ'} ✅",
            show_alert=True
        )
        await refresh_settings_view(callback_query)
    except Exception as e:
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {e}", show_alert=True)

# ─────────────────────────────
# 🔁 Toggle name swap
# ─────────────────────────────
async def cb_toggle_swap(client, callback_query):
    try:
        user_id = callback_query.from_user.id
        new_state = bool(int(callback_query.data.split("_")[-1]))
        await database.set_user_swap_state(user_id, new_state)
        await callback_query.answer(
            f"🔁 ꜱᴡᴀᴘ ᴍᴏᴅᴇ {'ᴇɴᴀʙʟᴇᴅ' if new_state else 'ᴅɪꜱᴀʙʟᴇᴅ'} ✅",
            show_alert=True
        )
        await refresh_settings_view(callback_query)
    except Exception as e:
        await callback_query.answer(f"❌ ᴇʀʀᴏʀ: {e}", show_alert=True)

# ─────────────────────────────
# 🔄 Refresh settings
# ─────────────────────────────
async def cb_refresh_settings(client, callback_query):
    await callback_query.answer("🔄 ʀᴇꜰʀᴇꜱʜɪɴɢ...", show_alert=False)
    await refresh_settings_view(callback_query)

# ─────────────────────────────
# Refresh message content
# ─────────────────────────────
async def refresh_settings_view(q):
    user_id = q.from_user.id
    prefix = await database.get_user_prefix(user_id)
    rename_folders = await database.get_user_folder_state(user_id)
    swap_mode = await database.get_user_swap_state(user_id)

    prefix_text = prefix if prefix else "❌ ɴᴏ ᴘʀᴇꜰɪx sᴇᴛ"
    folder_state = "✅ ᴇɴᴀʙʟᴇᴅ" if rename_folders else "🚫 ᴅɪꜱᴀʙʟᴇᴅ"
    swap_state = "✅ ᴇɴᴀʙʟᴇᴅ" if swap_mode else "🚫 ᴅɪꜱᴀʙʟᴇᴅ"

    text = (
        f"<b>⚙️ ᴜꜱᴇʀ ꜱᴇᴛᴛɪɴɢꜱ\n\n"
        f"🔤 ᴘʀᴇꜰɪx: {prefix_text}\n"
        f"📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ: {folder_state}\n"
        f"🔁 ɴᴀᴍᴇ ꜱᴡᴀᴘ: {swap_state}\n\n"
        f"ᴛᴀᴘ ᴛᴏ ᴛᴏɢɢʟᴇ ᴏᴘᴛɪᴏɴꜱ ↓</b>"
    )

    buttons = ButtonMaker()
    buttons.data_button("📂 ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ", f"toggle_folder_{int(not rename_folders)}")
    buttons.data_button("🔁 ɴᴀᴍᴇ ꜱᴡᴀᴘ", f"toggle_swap_{int(not swap_mode)}")
    buttons.data_button("🔄 ʀᴇꜰʀᴇꜱʜ", "refresh_settings")

    reply_markup = buttons.build_menu(1)
    await edit_message(q.message, text, reply_markup=reply_markup)

# ─────────────────────────────
# 🧩 Register handlers
# ─────────────────────────────
async def cb_debug(client, query):
    print("⚡ CALLBACK:", query.data)
    await query.answer("Got it ✅", show_alert=True)

TgClient.bot.add_handler(CallbackQueryHandler(cb_debug))

TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_folder, filters=regex("^toggle_folder_$")))
def register_settings_handlers():
    from .... import TgClient
    TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_folder, filters.regex(r"^toggle_folder_\d+$")))
    TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_swap, filters=regex(r"^toggle_swap_\d+$ ")))
    TgClient.bot.add_handler(CallbackQueryHandler(cb_refresh_settings, filters=regex(r"^refresh_settings$")))
