from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, Message
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

from .... import LOGGER
from ...telegram_helper.message_utils import send_message
from ....helper.ext_utils.db_handler import database
from ....helper.telegram_helper.button_build import ButtonMaker
from ....core.tg_client import TgClient
from ...ext_utils.bot_utils import cmd_exec

import os, re, asyncio, gc, time as t
from datetime import datetime
from config import OWNER_ID

# ─────────────────────────────
# /prefix
# ─────────────────────────────
async def prefix_command(_, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await send_message(
            message,
            "<b>⚙️ Usage:\n/prefix <prefix></b>"
        )
    await database.set_user_prefix(message.from_user.id, args[1].strip())
    await send_message(message, f"<b>✅ Prefix set to:</b> <code>{args[1]}</code>")


# ─────────────────────────────
# /rename — MegaCMD Rename
# ─────────────────────────────
async def rename_mega_command(_, message: Message):
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
    renamed = failed = 0

    msg = await send_message(message, "<b>🔐 Logging into Mega...</b>")
    start_time = t.time()

    try:
        # ─── LOGIN WITH TIMEOUT ───
        try:
            _, err, code = await asyncio.wait_for(cmd_exec(["mega-login", email, password]), timeout=30)
        except asyncio.TimeoutError:
            return await msg.edit_text("⏳ Mega login timed out. Check network or 2FA.")
        
        if code != 0:
            return await msg.edit_text(f"❌ Login failed:\n<code>{err}</code>")

        await msg.edit_text("<b>📂 Fetching files...</b>")

        # ─── LIST FILES WITH TIMEOUT ───
        try:
            out, err, code = await asyncio.wait_for(cmd_exec(["mega-ls", "-R"]), timeout=60)
        except asyncio.TimeoutError:
            await cmd_exec(["mega-logout"])
            return await msg.edit_text("⏳ Mega file listing timed out.")

        if code != 0:
            await cmd_exec(["mega-logout"])
            return await msg.edit_text(f"❌ Mega error:\n<code>{err}</code>")

        paths = [p.strip() for p in out.splitlines() if p.strip()]

        # ─── RENAME LOOP ───
        for path in paths:
            if renamed >= limit:
                break

            name = os.path.basename(path)
            is_folder = "." not in name

            if is_folder and not rename_folders:
                continue

            renamed += 1

            if swap_mode:
                try:
                    new_name = re.sub(r"@\w+", prefix, name)
                except Exception:
                    new_name = f"{prefix}_{renamed}"
            else:
                base, ext = os.path.splitext(name)
                new_name = f"{prefix}_{renamed}{ext}"

            new_path = os.path.join(os.path.dirname(path), new_name)

            try:
                _, err, code = await asyncio.wait_for(cmd_exec(["mega-mv", path, new_path]), timeout=20)
            except asyncio.TimeoutError:
                failed += 1
                LOGGER.error(f"Mega rename timeout: {path} → {new_name}")
                continue

            if code != 0:
                failed += 1
                LOGGER.error(f"Mega rename failed: {path} → {new_name} | {err}")

    finally:
        # ─── LOGOUT & CLEANUP ───
        try: await asyncio.wait_for(cmd_exec(["mega-logout"]), timeout=10)
        except Exception: pass
        gc.collect()

    # ─── UPDATE DATABASE ───
    try:
        await database.increment_user_rename_count(user_id, renamed)
    except Exception as e:
        LOGGER.warning(f"Rename count update failed: {e}")

    # ─── FINAL MESSAGE ───
    await msg.edit_text(
        f"<b>✅ Rename Completed</b>\n\n"
        f"🔢 <b>Renamed:</b> <code>{renamed}</code>\n"
        f"⚠️ <b>Failed:</b> <code>{failed}</code>\n"
        f"🔤 <b>Prefix:</b> <code>{prefix}</code>\n"
        f"📂 <b>Folder rename:</b> {'ON' if rename_folders else 'OFF'}\n"
        f"🔁 <b>Swap mode:</b> {'ON' if swap_mode else 'OFF'}\n"
        f"⏱ <b>Time:</b> <code>{round(t.time() - start_time, 2)}s</code>"
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
