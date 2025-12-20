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

import asyncio
import os, time as t, gc
from .... import LOGGER
from ...telegram_helper.message_utils import send_message
from ....helper.ext_utils.db_handler import database

async def rename_mega_command(_, message):
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        return await send_message(
            message,
            "<b>⚙️ Usage:</b>\n/rename <email> <password>"
        )

    email, password = args[1], args[2]
    user_id = message.from_user.id

    prefix = await database.get_user_prefix(user_id)
    rename_folders = await database.get_user_folder_state(user_id)
    swap_mode = await database.get_user_swap_state(user_id)
    is_premium = await database.is_user_premium(user_id)

    if not prefix:
        return await send_message(message, "❌ <b>No prefix set. Use /prefix first.</b>")

    limit = 10**9 if is_premium else 50

    msg = await send_message(message, "<b>🔐 Logging into Mega...</b>")
    start = t.time()

    try:
        # ─── LOGOUT FIRST ───
        proc = await asyncio.create_subprocess_shell(
            "mega-logout",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        # ─── LOGIN ───
        proc = await asyncio.create_subprocess_shell(
            f"mega-login {email} {password}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if proc.returncode != 0:
            return await msg.edit_text(f"❌ <b>Login failed:</b>\n<code>{err.decode()}</code>")

        await msg.edit_text("<b>📂 Renaming files...</b>")

        # ─── RENAME USING SHELL LOOP ───
        loop_cmd = f"""
i=1
mega-find / | while read file; do
    basename=$(basename "$file")
    dir=$(dirname "$file")
    ext="${{basename##*.}}"
    mega-mv "$file" "$dir/{prefix}_$i.$ext"
    i=$((i+1))
done
"""
        proc = await asyncio.create_subprocess_shell(
            loop_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        out, err = await proc.communicate()
        if err:
            LOGGER.warning(err.decode())

    finally:
        # ─── LOGOUT ───
        proc = await asyncio.create_subprocess_shell(
            "mega-logout",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        gc.collect()

    elapsed = round(t.time() - start, 2)
    await msg.edit_text(
        f"<b>✅ Rename Completed</b>\n"
        f"⏱ <b>Time:</b> <code>{elapsed}s</code>\n"
        f"🔤 <b>Prefix:</b> <code>{prefix}</code>"
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
