import os
import re
import asyncio
import gc
import time as t
import shutil

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.handlers import CallbackQueryHandler

from .... import LOGGER
from ....helper.ext_utils.db_handler import database
from ...telegram_helper.message_utils import send_message
from ....helper.telegram_helper.button_build import ButtonMaker
from ....core.tg_client import TgClient


# ─────────────────────────────
# MegaCMD SAFE RUNNER
# ─────────────────────────────
async def run_mega_cmd(cmd, timeout=60):
    if not shutil.which("mega-login"):
        return "", "MegaCMD not installed", -1

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "", "Command timeout", -1

        out = stdout.decode(errors="ignore")
        err = stderr.decode(errors="ignore")

        # 🔥 strip quota banners
        BAD = (
            "You have exceeded your available storage",
            "You have exeeded your available storage",
            "upgrade"
        )

        def clean(txt):
            return "\n".join(
                l for l in txt.splitlines()
                if not any(b in l for b in BAD)
            ).strip()

        return clean(out), clean(err), proc.returncode

    except Exception as e:
        return "", str(e), -1


# ─────────────────────────────
# /prefix
# ─────────────────────────────
async def prefix_command(_, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await send_message(
            message,
            "<b>⚙️ Usage:</b>\n<code>/prefix your_prefix</code>"
        )

    prefix = args[1].strip()
    await database.set_user_prefix(message.from_user.id, prefix)
    await send_message(
        message,
        f"<b>✅ Prefix set:</b> <code>{prefix}</code>"
    )

# ─────────────────────────────
# /rename — HANDLE BASED (FAST & FIXED)
# ─────────────────────────────
import asyncio, re, os, gc, time as t
from utils import send_message, run_mega_cmd, LOGGER, database
from pyrogram.types import Message

async def rename_mega_command(_, message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await send_message(
            message,
            "<b>⚙️ Usage:</b>\n<code>/rename email password</code>"
        )

    email, password = args[1], args[2]
    user_id = message.from_user.id

    prefix = await database.get_user_prefix(user_id)
    rename_folders = await database.get_user_folder_state(user_id)
    swap_mode = await database.get_user_swap_state(user_id)
    is_premium = await database.is_user_premium(user_id)

    if not prefix:
        return await send_message(message, "❌ <b>Set prefix first using /prefix</b>")

    limit = 10**9 if is_premium else 50
    renamed = 0
    failed = 0
    start_time = t.time()

    msg = await send_message(message, "<b>🔐 Resetting Mega session...</b>")

    # ─── LOGOUT ───
    await run_mega_cmd(["mega-logout"], timeout=10)

    # ─── LOGIN ───
    out, err, code = await run_mega_cmd(
        ["mega-login", email, password],
        timeout=40
    )
    if code != 0:
        return await msg.edit_text(f"❌ <b>Mega login failed</b>\n<code>{err or out}</code>")

    await msg.edit_text("<b>📂 Fetching file list...</b>")

    # ─── LIST FILES (HANDLE MODE) ───
    out, err, _ = await run_mega_cmd(
        ["mega-ls", "-R", "--show-handles"],
        timeout=180
    )

    entries = []
    for line in out.splitlines():
        line = line.strip()
        # Skip banners, warnings, or storage errors
        if not line or "exceeded your available storage" in line.lower():
            continue

        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue

        handle, name = parts
        # Validate Mega handle format
        if not handle.startswith("H:") and not handle.endswith("h"):
            continue

        # Remove extra chars
        name = name.lstrip("* ").strip()
        entries.append((handle, name))

    if not entries:
        await run_mega_cmd(["mega-logout"])
        return await msg.edit_text("❌ No files found to rename")

    await msg.edit_text(f"<b>✏️ Renaming {len(entries)} items...</b>")

    # ─── BATCH RENAME ───
    BATCH_SIZE = 20
    for handle, name in entries:
        if renamed >= limit:
            break

        is_folder = "." not in name
        if is_folder and not rename_folders:
            continue

        if name.startswith(prefix):
            continue

        try:
            if swap_mode:
                new_name = re.sub(r"@[\w\d_]+", prefix, name, count=1)
                if new_name == name:
                    new_name = f"{prefix}_{renamed+1}"
            else:
                base, ext = os.path.splitext(name)
                new_name = f"{prefix}_{renamed+1}{ext}"

            _, err, code = await run_mega_cmd(
                ["mega-mv", handle, new_name],
                timeout=15
            )

            if code == 0:
                renamed += 1
            else:
                failed += 1
                LOGGER.error(f"Rename failed: {name} → {new_name} | {err}")

        except Exception as e:
            failed += 1
            LOGGER.error(f"Rename error: {e}")

        # Yield for stability
        if (renamed + failed) % BATCH_SIZE == 0:
            await asyncio.sleep(0)

    # ─── LOGOUT ───
    await run_mega_cmd(["mega-logout"], timeout=10)
    gc.collect()

    try:
        await database.increment_user_rename_count(user_id, renamed)
    except Exception as e:
        LOGGER.warning(f"Rename stat update failed: {e}")

    await msg.edit_text(
        f"<b>✅ Rename Completed</b>\n\n"
        f"🔢 Renamed: <code>{renamed}</code>\n"
        f"⚠️ Failed: <code>{failed}</code>\n"
        f"🔤 Prefix: <code>{prefix}</code>\n"
        f"📂 Folder rename: {'ON' if rename_folders else 'OFF'}\n"
        f"🔁 Swap mode: {'ON' if swap_mode else 'OFF'}\n"
        f"⏱ Time: <code>{round(t.time() - start_time, 2)}s</code>"
    )



from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, Message
from pyrogram.handlers import CallbackQueryHandler

from .... import LOGGER
from ...telegram_helper.message_utils import send_message
from ....helper.ext_utils.db_handler import database
from ....helper.telegram_helper.button_build import ButtonMaker
from ....core.tg_client import TgClient
from ...ext_utils.bot_utils import cmd_exec

import os, re, asyncio, gc, time as t
from config import OWNER_ID

async def prefix_command(_, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await send_message(message, "<b>⚙️ Usage:\n/prefix &lt;prefix&gt;</b>")

    prefix = args[1].strip()
    await database.set_user_prefix(message.from_user.id, prefix)
    await send_message(message, f"<b>✅ Prefix set:</b> <code>{prefix}</code>")

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
TgClient.bot.add_handler(
    CallbackQueryHandler(cb_toggle_folder, filters.regex(r"^toggle_folder_"))
)
TgClient.bot.add_handler(
    CallbackQueryHandler(cb_toggle_swap, filters.regex(r"^toggle_swap_"))
)
