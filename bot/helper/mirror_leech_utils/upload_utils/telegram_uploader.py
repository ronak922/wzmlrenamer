import os
import math
import asyncio
import shutil
from pathlib import Path
from time import time
from zipfile import ZipFile, ZIP_DEFLATED
from logging import getLogger
from contextlib import suppress
from os import path as ospath, walk
from aioshutil import rmtree
from natsort import natsorted
from aiofiles.os import path as aiopath, remove
from pyrogram.errors import BadRequest, FloodWait
try:
    from pyrogram.errors import FloodPremiumWait
except ImportError:
    FloodPremiumWait = FloodWait
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from ....core.config_manager import Config
from ....core.tg_client import TgClient
from ...ext_utils.bot_utils import sync_to_async
from aiofiles import open as aio_open
from contextlib import suppress as _suppress
from asyncio.subprocess import PIPE
from ...ext_utils.status_utils import add_pretask, remove_pretask, MirrorStatus
LOGGER = getLogger(__name__)

# -----------------------------------------------------------
# TELEGRAM UPLOADER CLASS (Multi-ZIP workflow)
# -----------------------------------------------------------
class TelegramUploader:
    def __init__(self, listener, path):
        self._listener = listener
        self._path = path
        self._client = None
        self._start_time = time()
        self._thumb = self._listener.thumb or f"thumbnails/{listener.user_id}.jpg"
        self._msgs_dict = {}
        self._processed_bytes = 0
        self._last_uploaded = 0
        self._corrupted = 0
        self._total_files = 0
        self._is_corrupted = False
        self._sent_msg = None
        self._log_msg = None
        self._user_session = self._listener.user_transmission
        self._media_group = False
        self._bot_pm = False
        self._lprefix = ""
        self._lsuffix = ""
        self._lcaption = ""
        self._lfont = ""
        self._error = ""
        self._total_size = 0

    async def _update_status(self, new_status: str):
        try:
            self._listener.status = new_status
            if hasattr(self._listener, "update_status_message"):
                await self._listener.update_status_message()
            LOGGER.info(f"🔄 Status updated: {new_status}")
        except Exception as e:
            LOGGER.warning(f"Failed to update status: {e}")

    async def _set_manual_progress(self, processed_bytes: int, total_bytes: int):
        self._processed_bytes = processed_bytes
        self._total_size = total_bytes
        if hasattr(self._listener, "update_status_message"):
            await self._listener.update_status_message()

    async def _upload_progress(self, current, _):
        if self._listener.is_cancelled:
            if self._user_session:
                TgClient.user.stop_transmission()
            else:
                self._listener.client.stop_transmission()
        delta = current - self._last_uploaded
        self._processed_bytes += delta
        self._last_uploaded = current

    async def _user_settings(self):
        settings_map = {
            "MEDIA_GROUP": ("_media_group", False),
            "BOT_PM": ("_bot_pm", False),
            "LEECH_PREFIX": ("_lprefix", ""),
            "LEECH_SUFFIX": ("_lsuffix", ""),
            "LEECH_CAPTION": ("_lcaption", ""),
            "LEECH_FONT": ("_lfont", ""),
        }
        for key, (attr, default) in settings_map.items():
            setattr(self, attr, self._listener.user_dict.get(key) or getattr(Config, key, default))

        if self._thumb != "none" and not await aiopath.exists(self._thumb):
            self._thumb = None

    async def _msg_to_reply(self):
        is_group = getattr(self._listener.message.chat, "type", None)
        is_group = is_group and is_group.name in ("GROUP", "SUPERGROUP")
        dump_chat = getattr(Config, "LEECH_DUMP_CHAT", None)
        user_dest = getattr(self._listener, "leech_dest", None)
        msg = f"📦 <b>Leech Started</b>\nUser: {self._listener.user.mention} (#ID{self._listener.user_id})"

        try:
            if is_group and not dump_chat:
                dest = user_dest or self._listener.user_id
                self._sent_msg = await TgClient.bot.send_message(chat_id=dest, text=msg, disable_web_page_preview=True)
            else:
                self._sent_msg = await TgClient.bot.send_message(
                    chat_id=self._listener.up_dest or self._listener.user_id,
                    text=msg,
                    disable_web_page_preview=True,
                )
            return True
        except Exception as e:
            await self._listener.on_upload_error(str(e))
            return False

    async def _prepare_file(self, pre_file_, dirpath):
        cap_file = pre_file_
        if self._lprefix:
            cap_file = self._lprefix.replace(r"\s", " ") + cap_file
        if self._lsuffix:
            name, ext = ospath.splitext(cap_file)
            cap_file = name + self._lsuffix.replace(r"\s", " ") + ext
        return f"<{Config.LEECH_FONT}>{cap_file}</{Config.LEECH_FONT}>" if Config.LEECH_FONT else cap_file

    async def _rename_files(self, dirpath, base_name="@BhookiBhabhi"):
        valid_exts = [".mp4", ".mkv", ".jpg", ".png", ".jpeg"]
        counter = 1
        for root, _, files in os.walk(dirpath):
            for file in sorted(files):
                ext = os.path.splitext(file)[1].lower()
                if ext not in valid_exts:
                    continue
                old_path = os.path.join(root, file)
                new_path = os.path.join(root, f"{base_name} {counter}{ext}")
                try:
                    os.rename(old_path, new_path)
                    counter += 1
                except Exception as e:
                    LOGGER.warning(f"Rename failed for {file}: {e}")
        LOGGER.info(f"✅ Renamed {counter - 1} files in {dirpath}")

    # ---------------------------------------------
    # Multi-ZIP (<=1.9GB each, standalone)
    # ---------------------------------------------
    async def _zip_before_upload(self, file_path, base_name="@BhookiBhabhi x @PookieCommunity"):
        await self._update_status(MirrorStatus.STATUS_ARCHIVE)

        if file_path.endswith(".zip"):return [file_path]

        MAX_ZIP_MB = 1750  # 1.75GB
        zip_base = base_name.strip().replace(" ", "_")
        zip_dir = os.path.dirname(file_path)
        folder_name = os.path.basename(file_path.rstrip("/"))
        LOGGER.info(f"📦 Compressing '{folder_name}' into <= {MAX_ZIP_MB}MB chunks")

        file_list = []
        total_size = 0
        for root, _, files in os.walk(file_path):
            for f in files:
                f_path = os.path.join(root, f)
                try:
                    size = os.path.getsize(f_path)
                except Exception:
                    size = 0
                total_size += size
                file_list.append((f_path, os.path.relpath(f_path, file_path)))

        processed_bytes = 0
        zip_index = 1
        zip_part_paths = []
        current_size = 0
        zip_path = os.path.join(zip_dir, f"{zip_base}_part{zip_index:03}.zip")
        zipf = ZipFile(zip_path, "w", ZIP_DEFLATED)

        async def progress_update():
            await self._set_manual_progress(processed_bytes, total_size)

        for f_path, arcname in file_list:
            f_size = os.path.getsize(f_path)
            if current_size + f_size > MAX_ZIP_MB * 1024 * 1024:
                zipf.close()
                LOGGER.info(f"✅ Created: {zip_path}")
                zip_part_paths.append(zip_path)
                zip_index += 1
                zip_path = os.path.join(zip_dir, f"{zip_base}_part{zip_index:03}.zip")
                zipf = ZipFile(zip_path, "w", ZIP_DEFLATED)
                current_size = 0

            zipf.write(f_path, arcname)
            current_size += f_size
            processed_bytes += f_size

            if processed_bytes % (50 * 1024 * 1024) < f_size:
                asyncio.create_task(progress_update())

        zipf.close()
        zip_part_paths.append(zip_path)
        LOGGER.info(f"✅ Created: {zip_path}")
        await progress_update()
        LOGGER.info(f"✨ Finished ZIP compression into {len(zip_part_paths)} parts")

        return zip_part_paths

    # ---------------------------------------------
    # Upload logic
    # ---------------------------------------------
    async def upload(self):
        await self._user_settings()
        if not await self._msg_to_reply():
            return

        if not await aiopath.exists(self._path):
            return await self._listener.on_upload_error("❌ Folder not found.")

        pretask = await add_pretask(self._path, MirrorStatus.STATUS_RENAME, self._listener)
        await self._rename_files(self._path, base_name="@BhookiBhabhi")

        pretask._status = MirrorStatus.STATUS_ARCHIVE
        zip_paths = await self._zip_before_upload(self._path)
        await remove_pretask(pretask)
        await self._update_status(MirrorStatus.STATUS_UPLOAD)

        for idx, zip_path in enumerate(zip_paths, start=1):
            zip_name = os.path.basename(zip_path)
            caption = await self._prepare_file(f"{zip_name} (Part {idx}/{len(zip_paths)})", self._path)
            try:
                await self._upload_file(caption, zip_name, zip_path)
            except Exception as err:
                LOGGER.error(f"Upload failed for {zip_path}: {err}", exc_info=True)
                self._corrupted += 1
            finally:
                if await aiopath.exists(zip_path):
                    await remove(zip_path)

        await rmtree(self._path, ignore_errors=True)
        await self._listener.on_upload_complete(None, self._msgs_dict, self._total_files, self._corrupted)
        LOGGER.info(f"✅ Leech Completed: {self._listener.name}")

    # ---------------------------------------------
    # Upload individual file/document
    # ---------------------------------------------
    @retry(wait=wait_exponential(multiplier=2, min=4, max=8),
           stop=stop_after_attempt(3),
           retry=retry_if_exception_type(Exception))
    async def _upload_file(self, caption, file, o_path, force_document=True):
        thumb = self._thumb if self._thumb and await aiopath.exists(self._thumb) else None
        dest = self._listener.leech_dest or self._listener.user_id
        if not isinstance(dest, int) and str(dest).lstrip("-").isdigit():
            dest = int(dest)

        try:
            await TgClient.bot.send_document(
                chat_id=dest,
                document=o_path,
                caption=caption,
                thumb=thumb,
                force_document=True,
                disable_notification=True,
                progress=self._upload_progress,
            )

        except (FloodWait, FloodPremiumWait) as f:
            LOGGER.warning(str(f))
            await asyncio.sleep(f.value * 1.3)
            return await self._upload_file(caption, file, o_path, force_document)

        except Exception as err:
            LOGGER.error(f"{err}. Path: {o_path}", exc_info=True)
            if isinstance(err, BadRequest):
                return await self._upload_file(caption, file, o_path, True)
            raise err

    async def cancel_task(self):
        self._listener.is_cancelled = True
        LOGGER.info(f"⛔ Upload Cancelled: {self._listener.name}")
        await self._listener.on_upload_error("Upload cancelled!")

    @property
    def speed(self):
        try:
            return self._processed_bytes / (time() - self._start_time)
        except ZeroDivisionError:
            return 0

    @property
    def processed_bytes(self):
        return self._processed_bytes
