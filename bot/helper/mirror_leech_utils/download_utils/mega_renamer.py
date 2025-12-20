import os
import re
import asyncio
import gc
import time as t
import shutil

from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup
from pyrogram.handlers import CallbackQueryHandler

from mega import Mega  # Correct Mega SDK import

from .... import LOGGER
from ....helper.ext_utils.db_handler import database
from ...telegram_helper.message_utils import send_message
from ....helper.telegram_helper.button_build import ButtonMaker
from ....core.tg_client import TgClient
from ...ext_utils.bot_utils import sync_to_async  # helper to wrap sync calls in async

# ─────────────────────────────
# /rename COMMAND
# ─────────────────────────────
async def rename_mega_command(client, message: Message):
    try:
        args = message.text.split(maxsplit=3)
        if len(args) < 3:
            return await send_message(
                message,
                "<b>⚙️ Usage:</b>\n/rename <email> <password>\n\n<b>📘 Example:</b>\n/rename test@gmail.com mypass"
            )

        email, password = args[1], args[2]
        user_id = message.from_user.id

        rename_prefix = await database.get_user_prefix(user_id)
        rename_folders = await database.get_user_folder_state(user_id)
        swap_mode = await database.get_user_swap_state(user_id)
        is_premium = await database.is_user_premium(user_id)

        user_type_text = "💎 <b>Premium User</b>" if is_premium else "🆓 <b>Free User</b>"
        msg = await send_message(message, f"<b>🔐 Logging into MEGA...</b>\n\n{user_type_text}")
        start_time = t.time()

        # Initialize Mega SDK
        mega = Mega()
        try:
            api = await sync_to_async(mega.login)(email, password)
        except Exception as e:
            await msg.edit_text(f"❌ Login failed:\n<code>{e}</code>")
            return

        await msg.edit_text(f"<b>✅ Login successful</b>\n📂 Fetching structure...\n\n{user_type_text}")

        files = await sync_to_async(api.get_files)()  # all files/folders

        limit = 999999999 if is_premium else 50
        renamed, failed = 0, 0
        counter = 0

        # ─── Recursive rename function
        async def traverse(files_dict):
            nonlocal renamed, failed, counter
            for fid, info in files_dict.items():
                if counter >= limit:
                    break
                try:
                    name = info.get('a', {}).get('n')  # file/folder name
                    is_folder = info.get('t') == 1
                except Exception:
                    failed += 1
                    continue

                # Skip folders if not renaming folders
                if is_folder and not rename_folders:
                    children = {k: v for k, v in files_dict.items() if v.get('p') == fid}
                    if children:
                        await traverse(children)
                    continue

                # Rename logic
                if rename_prefix and name and not name.startswith(rename_prefix):
                    counter += 1
                    new_name = name
                    if swap_mode:
                        new_name = re.sub(r"@\w+", rename_prefix, name)
                        if new_name == name:
                            new_name = f"{rename_prefix}_{counter}"
                    else:
                        base, ext = os.path.splitext(name)
                        new_name = f"{rename_prefix}_{counter}{ext}" if ext else f"{rename_prefix}_{counter}"

                    try:
                        await sync_to_async(api.rename)(fid, new_name)
                        renamed += 1
                    except Exception:
                        failed += 1
                        continue  # skip quota/missing file errors

                # Recurse into subfolders
                if is_folder:
                    children = {k: v for k, v in files_dict.items() if v.get('p') == fid}
                    if children:
                        await traverse(children)

        await traverse(files)

        time_taken = round(t.time() - start_time, 2)
        await msg.edit_text(
            f"<b>✅ Rename Completed</b>\n\n"
            f"🔢 Renamed: <code>{renamed}</code>\n"
            f"⚠️ Failed/Skipped: <code>{failed}</code>\n"
            f"🔤 Prefix: <code>{rename_prefix or 'None'}</code>\n"
            f"📂 Folder rename: {'ON' if rename_folders else 'OFF'}\n"
            f"🔁 Swap mode: {'ON' if swap_mode else 'OFF'}\n"
            f"⏱ Time: <code>{time_taken}s</code>"
        )

        try:
            await database.increment_user_rename_count(user_id, renamed)
        except Exception as err:
            LOGGER.warning(f"Failed to update rename count for {user_id}: {err}")

        # Cleanup
        try:
            await sync_to_async(api.logout)()
        except Exception:
            pass
        del mega, api
        gc.collect()

    except Exception as e:
        LOGGER.error(f"Mega rename error: {e}", exc_info=True)
        await send_message(message, f"🚨 Error occurred:\n<code>{e}</code>")

# ─────────────────────────────
# /prefix COMMAND
# ─────────────────────────────
async def prefix_command(_, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await send_message(message, "<b>⚙️ Usage:\n/prefix &lt;prefix&gt;</b>")

    prefix = args[1].strip()
    await database.set_user_prefix(message.from_user.id, prefix)
    await send_message(message, f"<b>✅ Prefix set:</b> <code>{prefix}</code>")

# ─────────────────────────────
# /settings COMMAND
# ─────────────────────────────
async def settings_command(client, message):
    await send_settings_view(client, message, message.from_user.id, edit=False)

async def send_settings_view(client, message, user_id, edit=False):
    prefix = await database.get_user_prefix(user_id)
    folders = await database.get_user_folder_state(user_id)
    swap = await database.get_user_swap_state(user_id)

    text = (
        f"<b>⚙️ Settings</b>\n\n"
        f"🔤 Prefix: <code>{prefix or 'None'}</code>\n"
        f"📂 Rename Folders: {'✅' if folders else '❌'}\n"
        f"🔁 Swap Mode: {'✅' if swap else '❌'}"
    )

    buttons = ButtonMaker()
    buttons.data_button("📂 Toggle Folder", f"toggle_folder_{int(not folders)}")
    buttons.data_button("🔁 Toggle Swap", f"toggle_swap_{int(not swap)}")
    markup = buttons.build_menu(1)

    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.reply_text(text, reply_markup=markup)

# ─────────────────────────────
# CALLBACKS FOR TOGGLE BUTTONS
# ─────────────────────────────
async def cb_toggle_folder(_, q):
    state = bool(int(q.data.split("_")[-1]))
    await database.set_user_folder_state(q.from_user.id, state)
    await q.answer("Updated")
    await send_settings_view(_, q.message, q.from_user.id, edit=True)

async def cb_toggle_swap(_, q):
    state = bool(int(q.data.split("_")[-1]))
    await database.set_user_swap_state(q.from_user.id, state)
    await q.answer("Updated")
    await send_settings_view(_, q.message, q.from_user.id, edit=True)


# ─────────────────────────────
# Register CALLBACK HANDLERS
# ─────────────────────────────
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_folder, filters.regex(r"^toggle_folder_")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_swap, filters.regex(r"^toggle_swap_")))
