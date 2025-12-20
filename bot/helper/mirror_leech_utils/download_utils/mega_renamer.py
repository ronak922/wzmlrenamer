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


# ─────────────────────────────
# /prefix
# ─────────────────────────────
async def prefix_command(_, message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await send_message(message, "<b>⚙️ Usage:\n/prefix &lt;prefix&gt;</b>")

    prefix = args[1].strip()
    await database.set_user_prefix(message.from_user.id, prefix)
    await send_message(message, f"<b>✅ Prefix set:</b> <code>{prefix}</code>")

import os, re, asyncio, gc, time as t
from pyrogram.types import Message
from .... import LOGGER
from ....helper.ext_utils.db_handler import database
from ...telegram_helper.message_utils import send_message
from ...ext_utils.bot_utils import cmd_exec  # replace with run_mega_cmd wrapper
from ....core.tg_client import TgClient

# ─────────────────────────────
# MegaCMD wrapper with quota skip
# ─────────────────────────────
import shutil

async def run_mega_cmd(cmd, timeout=30):
    """Run MegaCMD asynchronously, ignore quota banners."""
    if not shutil.which("mega-login"):
        raise RuntimeError("MegaCMD not installed or not in PATH")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "", f"Timeout after {timeout}s", -1

        out = stdout.decode().strip()
        err = stderr.decode().strip()

        # Remove quota warnings
        out = "\n".join(line for line in out.splitlines()
                        if "You have exceeded your available storage" not in line)
        err = "\n".join(line for line in err.splitlines()
                        if "You have exceeded your available storage" not in line)

        return out, err, proc.returncode

    except Exception as e:
        return "", str(e), -1


# ─────────────────────────────
# /rename — MegaCMD ONLY
# ─────────────────────────────
async def rename_mega_command(_, message: Message):
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        return await send_message(message, "<b>⚙️ Usage:</b>\n/rename &lt;email&gt; &lt;password&gt;")

    email, password = args[1], args[2]
    user_id = message.from_user.id

    prefix = await database.get_user_prefix(user_id)
    rename_folders = await database.get_user_folder_state(user_id)
    swap_mode = await database.get_user_swap_state(user_id)
    is_premium = await database.is_user_premium(user_id)

    if not prefix:
        return await send_message(message, "❌ <b>Set prefix first using /prefix</b>")

    limit = 10**9 if is_premium else 50
    renamed, failed = 0, 0

    msg = await send_message(message, "<b>🔐 Resetting Mega session...</b>")
    start_time = t.time()

    # ─── LOGOUT ANY EXISTING SESSION ───
    try:
        await run_mega_cmd(["mega-logout"], timeout=10)
    except Exception:
        pass

    # ─── LOGIN ───
    out, err, code = await run_mega_cmd(["mega-login", email, password], timeout=30)
    if code != 0:
        return await msg.edit_text(f"❌ Mega login failed:\n<code>{err}</code>")

    await msg.edit_text("<b>📂 Fetching file list...</b>")

    # ─── LIST FILES ───
    out, err, code = await run_mega_cmd(["mega-ls", "-R", "--no-header"], timeout=90)
    if code != 0:
        await run_mega_cmd(["mega-logout"])
        return await msg.edit_text(f"❌ Mega error:\n<code>{err}</code>")

    paths = [p.strip() for p in out.splitlines() if p.strip()]
    await msg.edit_text("<b>✏️ Renaming files...</b>")

    # ─── RENAME LOOP ───
    for path in paths:
        if renamed >= limit:
            break

        name = os.path.basename(path)
        parent = os.path.dirname(path)
        is_folder = "." not in name

        if is_folder and not rename_folders:
            continue
        if name.startswith(prefix):
            continue

        try:
            if swap_mode:
                new_name = re.sub(r"@[\w\d_]+", prefix, name, count=1)
                if new_name == name:
                    new_name = f"{prefix}_{renamed + 1}"
            else:
                base, ext = os.path.splitext(name)
                new_name = f"{prefix}_{renamed + 1}{ext}"

            new_path = os.path.join(parent, new_name)

            _, err, code = await run_mega_cmd(["mega-mv", path, new_path], timeout=20)
            if code == 0:
                renamed += 1
            else:
                failed += 1
                LOGGER.error(f"❌ Rename failed: {path} → {new_name} | {err}")

        except asyncio.TimeoutError:
            failed += 1
            LOGGER.error(f"⏱ Rename timeout: {path}")
        except Exception as e:
            failed += 1
            LOGGER.error(f"💥 Rename error: {e}")

    # ─── LOGOUT CLEAN ───
    try:
        await run_mega_cmd(["mega-logout"], timeout=10)
    except Exception:
        pass

    gc.collect()

    # ─── UPDATE DB ───
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
TgClient.bot.add_handler(
    CallbackQueryHandler(cb_toggle_folder, filters.regex(r"^toggle_folder_"))
)
TgClient.bot.add_handler(
    CallbackQueryHandler(cb_toggle_swap, filters.regex(r"^toggle_swap_"))
)
