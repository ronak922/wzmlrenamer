from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from pyrogram.handlers import CallbackQueryHandler

from .... import LOGGER
# from ...listeners.mega_listener import AsyncMega
from ...telegram_helper.message_utils import send_message
from ....helper.ext_utils.db_handler import database
from ....helper.telegram_helper.button_build import ButtonMaker
from ....core.tg_client import TgClient
from ...ext_utils.bot_utils import cmd_exec

import os, re, asyncio, gc
import time as t
from datetime import datetime
from config import OWNER_ID

# ─────────────────────────────
# /prefix
# ─────────────────────────────
async def prefix_command(_, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await send_message(
            message,
            "<b>⚙️ Usage:\n/prefix <prefix></b>"
        )
    await database.set_user_prefix(message.from_user.id, args[1].strip())
    await send_message(message, f"<b>✅ Prefix set to:</b> <code>{args[1]}</code>")

import asyncio, os, re, gc, time as t
from .... import LOGGER
from ...telegram_helper.message_utils import send_message
from ....helper.ext_utils.db_handler import database

import asyncio, os, re, gc, time as t
from config import OWNER_ID
from .... import LOGGER
from ....helper.telegram_helper.message_utils import send_message
from ....helper.ext_utils.db_handler import database

import asyncio
import os
import re
import time as t

async def rename_mega_command(_, message):
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        return await send_message(message, "<b>⚙️ Usage:</b>\n/rename <email> <password>")

    email, password = args[1], args[2]
    user_id = message.from_user.id

    prefix = await database.get_user_prefix(user_id)
    rename_folders = await database.get_user_folder_state(user_id)
    swap_mode = await database.get_user_swap_state(user_id)
    is_premium = await database.is_user_premium(user_id)

    if not prefix:
        return await send_message(message, "❌ <b>No prefix set. Use /prefix first.</b>")

    limit = 10**9  # effectively unlimited
    renamed = failed = 0

    msg = await send_message(
        message,
        "<b>🔐 Logging into Mega...\nIf stuck for >2 min, please retry...</b>"
    )
    start = t.time()

    try:
        # ─── LOGOUT FIRST ───
        proc = await asyncio.create_subprocess_shell(
            "mega-logout 2>/dev/null || true",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        # ─── LOGIN ───
        proc = await asyncio.create_subprocess_shell(
            f"mega-login {email} {password} 2>/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            return await msg.edit_text(f"❌ <b>Login failed:</b>\n<code>{err.decode()}</code>")

        await msg.edit_text("<b>📂 Fetching files...</b>")

        # ─── GET FILES RECURSIVELY ───
        proc = await asyncio.create_subprocess_shell(
            "mega-find /",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise Exception(err.decode())

        paths = [p.strip() for p in out.decode().splitlines() if p.strip()]
        total_paths = len(paths)
        await msg.edit_text(f"<b>📂 Found {total_paths} files/folders. Renaming...</b>")

        # ─── CONCURRENT RENAME ───
        semaphore = asyncio.Semaphore(50)  # limit concurrency

        async def rename_with_retry(path, new_path, retries=3, delay=3):
            for attempt in range(retries):
                try:
                    # Try renaming the file
                    proc = await asyncio.create_subprocess_shell(
                        f'mega-mv "{path}" "{new_path}" 2>/dev/null',
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    out, err = await proc.communicate()
                    if proc.returncode == 0:
                        return True  # Success
                    else:
                        # Log the failure and retry
                        LOGGER.warning(f"Attempt {attempt + 1} failed for {path} → {new_path}: {err.decode() if err else 'Unknown error'}")
                        if attempt < retries - 1:
                            await asyncio.sleep(delay)
                        else:
                            return False
                except Exception as e:
                    LOGGER.error(f"Error while renaming {path}: {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(delay)
                    else:
                        return False

        async def rename_path(i, path):
            nonlocal renamed, failed
            async with semaphore:
                name = os.path.basename(path)
                is_folder = "." not in name
                if is_folder and not rename_folders:
                    return

                new_name = f"{prefix}_{i}{os.path.splitext(name)[1]}"
                if swap_mode and "@" in name:
                    new_name = re.sub(r"@\w+", prefix, name)

                new_path = os.path.join(os.path.dirname(path), new_name)

                # Check if the file already exists with the new name
                check_proc = await asyncio.create_subprocess_shell(
                    f"mega-find \"{os.path.dirname(path)}\" | grep -qxF \"{new_name}\"",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                check_out, check_err = await check_proc.communicate()

                if check_proc.returncode == 0:
                    # File with the new name exists, skip renaming or append suffix
                    new_name = f"{prefix}_{i}_duplicate{os.path.splitext(name)[1]}"
                    new_path = os.path.join(os.path.dirname(path), new_name)

                # Now proceed with renaming, use retry logic
                if await rename_with_retry(path, new_path):
                    renamed += 1
                    LOGGER.info(f"Successfully renamed: {path} → {new_name}")
                else:
                    failed += 1
                    LOGGER.warning(f"Failed to rename: {path} → {new_name}")

        tasks = [rename_path(i + 1, path) for i, path in enumerate(paths[:limit])]
        await asyncio.gather(*tasks)

    finally:
        proc = await asyncio.create_subprocess_shell(
            "mega-logout 2>/dev/null || true",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        gc.collect()

    try:
        await database.increment_user_rename_count(user_id, renamed)
    except Exception as e:
        LOGGER.warning(f"Rename count update failed: {e}")

    elapsed = round(t.time() - start, 2)
    await msg.edit_text(
        f"<b>✅ ʀᴇɴᴀᴍᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ</b>\n"
        f"🔢 <b>ʀᴇɴᴀᴍᴇᴅ:</b> <code>{renamed}</code>\n"
        f"⚠️ <b>ꜰᴀɪʟᴇᴅ:</b> <code>{failed}</code>\n"
        f"🔤 <b>ᴘʀᴇꜰɪx:</b> <code>{prefix}</code>\n"
        f"📂 <b>ꜰᴏʟᴅᴇʀ ʀᴇɴᴀᴍᴇ:</b> {'ᴏɴ' if rename_folders else 'ᴏғғ'}\n"
        f"🔁 <b>sᴡᴀᴘ ᴍᴏᴅᴇ:</b> {'ᴏɴ' if swap_mode else 'ᴏғғ'}\n"
        f"⏱ <b>ᴛɪᴍᴇ:</b> <code>{elapsed}s</code>"
    )


# ─────────────────────────────
# /settings
# ─────────────────────────────
async def settings_command(client, message):
    await send_settings_view(client, message, message.from_user.id)


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
# Callbacks
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
# Register handlers
# ─────────────────────────────
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_folder, filters.regex(r"^toggle_folder_")))
TgClient.bot.add_handler(CallbackQueryHandler(cb_toggle_swap, filters.regex(r"^toggle_swap_")))
