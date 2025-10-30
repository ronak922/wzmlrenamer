from asyncio import gather, iscoroutinefunction
from html import escape
from re import findall
from time import time

from psutil import cpu_percent, disk_usage, virtual_memory

from ... import (
    DOWNLOAD_DIR,
    bot_cache,
    bot_start_time,
    status_dict,
    task_dict,
    task_dict_lock,
)
from ...core.config_manager import Config
from ..telegram_helper.button_build import ButtonMaker

SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


class MirrorStatus:
    STATUS_UPLOAD = "⏫ ᴜᴘʟᴏᴀᴅɪɴɢ"
    STATUS_DOWNLOAD = "⏬ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ"
    STATUS_CLONE = "ᴄʟᴏɴᴇ"
    STATUS_QUEUEDL = "Qᴜᴇᴜᴇᴅʟ"
    STATUS_QUEUEUP = "Qᴜᴇᴜᴇᴜᴘ"
    STATUS_PAUSED = "ᴘᴀᴜsᴇ"
    STATUS_ARCHIVE = "🗃️ ᴀʀᴄʜɪᴠᴇɪɴɢ"
    STATUS_EXTRACT = "ᴇxᴛʀᴀᴄᴛɪɴɢ"
    STATUS_SPLIT = "✂️ sᴘʟɪᴛɪɴɢ"
    STATUS_CHECK = "ᴄʜᴇᴄᴋᴜᴘ"
    STATUS_SEED = "sᴇᴇᴅ"
    STATUS_SAMVID = "sᴀᴍᴠɪᴅ"
    STATUS_CONVERT = "ᴄᴏɴvᴇʀᴛ"
    STATUS_FFMPEG = "ғғᴍᴘᴇɢ"
    STATUS_YT = "YᴏᴜTᴜʙᴇ"
    STATUS_METADATA = "ᴍᴇᴛᴀᴅᴀᴛᴀ"
    STATUS_RENAME = "⚡ʀᴇɴᴀᴍᴇɪɴɢ"

# ---------------------- PRETASK HANDLER ----------------------

class PreTask:
    def __init__(self, name, status, listener):
        self._name = name
        self._status = status
        self._listener = listener
        self._start_time = time()

    def gid(self):
        return f"pretask-{int(self._start_time)}"

    def name(self):
        return self._name

    def status(self):
        return self._status

    def size(self):
        return "—"

    def progress(self):
        return 100

    def speed(self):
        return "—"

    def eta(self):
        return "—"


async def add_pretask(name, status, listener):
    async with task_dict_lock:
        tk = PreTask(name, status, listener)
        task_dict[tk.gid()] = tk
    return tk


async def remove_pretask(task):
    async with task_dict_lock:
        if task.gid() in task_dict:
            del task_dict[task.gid()]


class EngineStatus:
    def __init__(self):
        self.STATUS_ARIA2 = f"ᴀʀɪᴀ2 ᴠ{bot_cache['eng_versions']['aria2']}"
        self.STATUS_AIOHTTP = f"ᴀɪᴏʜᴛᴘ ᴠ{bot_cache['eng_versions']['aiohttp']}"
        self.STATUS_GDAPI = f"ɢᴏᴏɢʟᴇ-ᴀᴘɪ ᴠ{bot_cache['eng_versions']['gapi']}"
        self.STATUS_QBIT = f"ϲᴏᴏᴋɪᴇ ᴠ{bot_cache['eng_versions']['qBittorrent']}"
        self.STATUS_TGRAM = f"ᴘʏʀᴏ ᴠ{bot_cache['eng_versions']['pyrofork']}"
        self.STATUS_MEGA = f"ᴍᴇɢᴀᴀᴘɪ ᴠ{bot_cache['eng_versions']['mega']}"
        self.STATUS_YTDLP = f"ʏᴛ-ᴅʟᴘ ᴠ{bot_cache['eng_versions']['yt-dlp']}"
        self.STATUS_FFMPEG = f"ғғᴍᴘᴇɢ ᴠ{bot_cache['eng_versions']['ffmpeg']}"
        self.STATUS_7Z = f"7ᴢ ᴠ{bot_cache['eng_versions']['7z']}"
        self.STATUS_RCLONE = f"ʀᴄʟᴏɴᴇ ᴠ{bot_cache['eng_versions']['rclone']}"
        self.STATUS_SABNZBD = f"sᴀʙɴᴢʙᴅ+ ᴠ{bot_cache['eng_versions']['SABnzbd+']}"
        self.STATUS_QUEUE = "ϲʏsᴛᴇᴍ ϲᴏᴏʟᴍᴇ ʋ2"  # "Queue v2"
        self.STATUS_JD = "ᴊᴅᴏᴡɴʟᴏᴀᴅᴇʀ ᴠ2"  # "JDownloader v2"
        self.STATUS_YT = "ʏᴏᴜᴛᴜʙᴇ-ᴀᴘɪ"  # "Youtube-Api"
        self.STATUS_METADATA = "ᴍᴇᴛᴀᴅᴀᴛᴀ"  # "Metadata"


STATUSES = {
    "ALL": "All",
    "DL": MirrorStatus.STATUS_DOWNLOAD,
    "UP": MirrorStatus.STATUS_UPLOAD,
    "QD": MirrorStatus.STATUS_QUEUEDL,
    "QU": MirrorStatus.STATUS_QUEUEUP,
    "AR": MirrorStatus.STATUS_ARCHIVE,
    "EX": MirrorStatus.STATUS_EXTRACT,
    "SD": MirrorStatus.STATUS_SEED,
    "CL": MirrorStatus.STATUS_CLONE,
    "CM": MirrorStatus.STATUS_CONVERT,
    "SP": MirrorStatus.STATUS_SPLIT,
    "SV": MirrorStatus.STATUS_SAMVID,
    "FF": MirrorStatus.STATUS_FFMPEG,
    "PA": MirrorStatus.STATUS_PAUSED,
    "CK": MirrorStatus.STATUS_CHECK,
}

async def get_task_by_gid(gid: str):
    async with task_dict_lock:
        for tk in task_dict.values():
            if hasattr(tk, "seeding"):
                await tk.update()
            if tk.gid() == gid:
                return tk
        return None


async def get_specific_tasks(status, user_id):
    if status == "All":
        if user_id:
            return [tk for tk in task_dict.values() if tk.listener.user_id == user_id]
        else:
            return list(task_dict.values())
    tasks_to_check = (
        [tk for tk in task_dict.values() if tk.listener.user_id == user_id]
        if user_id
        else list(task_dict.values())
    )
    coro_tasks = []
    coro_tasks.extend(tk for tk in tasks_to_check if iscoroutinefunction(tk.status))
    coro_statuses = await gather(*[tk.status() for tk in coro_tasks])
    result = []
    coro_index = 0
    for tk in tasks_to_check:
        if tk in coro_tasks:
            st = coro_statuses[coro_index]
            coro_index += 1
        else:
            st = tk.status()
        if (st == status) or (
            status == MirrorStatus.STATUS_DOWNLOAD and st not in STATUSES.values()
        ):
            result.append(tk)
    return result


async def get_all_tasks(req_status: str, user_id):
    async with task_dict_lock:
        return await get_specific_tasks(req_status, user_id)


def get_raw_file_size(size):
    num, unit = size.split()
    return int(float(num) * (1024 ** SIZE_UNITS.index(unit)))


def get_readable_file_size(size_in_bytes):
    if not size_in_bytes:
        return "0B"

    index = 0
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1

    return f"{size_in_bytes:.2f}{SIZE_UNITS[index]}"


def get_readable_time(seconds: int):
    periods = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            result += f"{int(period_value)}{period_name}"
    return result


def get_raw_time(time_str: str) -> int:
    time_units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(
        int(value) * time_units[unit]
        for value, unit in findall(r"(\d+)([dhms])", time_str)
    )


def time_to_seconds(time_duration):
    try:
        parts = time_duration.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(float, parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = map(float, parts)
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = float(parts[0])
        else:
            return 0
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return 0


def speed_string_to_bytes(size_text: str):
    size = 0
    size_text = size_text.lower()
    if "k" in size_text:
        size += float(size_text.split("k")[0]) * 1024
    elif "m" in size_text:
        size += float(size_text.split("m")[0]) * 1048576
    elif "g" in size_text:
        size += float(size_text.split("g")[0]) * 1073741824
    elif "t" in size_text:
        size += float(size_text.split("t")[0]) * 1099511627776
    elif "b" in size_text:
        size += float(size_text.split("b")[0])
    return size


def get_progress_bar_string(pct, bar_length=10):
    try:
        pct = float(str(pct).strip("%"))
    except Exception:
        pct = 0.0

    p = min(max(pct, 0), 100)

    pulse = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "🟤"]
    # Prevent out-of-range error
    index = int(p // (100 / len(pulse)))
    index = min(index, len(pulse) - 1)
    pulse_block = pulse[index]

    filled_blocks = int(p // (100 / bar_length))
    p_str = pulse_block * filled_blocks + "⬡" * (bar_length - filled_blocks)

    return f"[{p_str}] {p:.2f}%"



async def get_readable_message(sid, is_user, page_no=1, status="All", page_step=1):
    msg = ""
    button = None

    tasks = await get_specific_tasks(status, sid if is_user else None)

    STATUS_LIMIT = Config.STATUS_LIMIT
    tasks_no = len(tasks)
    pages = (max(tasks_no, 1) + STATUS_LIMIT - 1) // STATUS_LIMIT
    if page_no > pages:
        page_no = (page_no - 1) % pages + 1
        status_dict[sid]["page_no"] = page_no
    elif page_no < 1:
        page_no = pages - (abs(page_no) % pages)
        status_dict[sid]["page_no"] = page_no
    start_position = (page_no - 1) * STATUS_LIMIT

    for index, task in enumerate(
        tasks[start_position : STATUS_LIMIT + start_position], start=1
    ):
        if status != "All":
            tstatus = status
        elif iscoroutinefunction(task.status):
            tstatus = await task.status()
        else:
            tstatus = task.status()
        msg += f"<b>{index + start_position}.</b> "
        msg += f"<b><i>{escape(f'{task.name()}')}</i></b>"
        if task.listener.subname:
            msg += f"\n┖ <b>sᴜʙ ɴᴀᴍᴇ</b> → <i>{task.listener.subname}</i>"
        elapsed = time() - task.listener.message.date.timestamp()

        msg += f"\n\n<b>ᴛᴀsᴋ ʙʏ {task.listener.message.from_user.mention(style='html')} </b> ( #ID{task.listener.message.from_user.id} )"
        if task.listener.is_super_chat:
            msg += f" <i>[<a href='{task.listener.message.link}'>ʟɪɴᴋ</a>]</i>"

        if (
            tstatus not in [MirrorStatus.STATUS_SEED, MirrorStatus.STATUS_QUEUEUP]
            and task.listener.progress
        ):
            progress = task.progress()
            msg += f"\n┟ {get_progress_bar_string(progress)}"
            if task.listener.subname:
                subsize = f" / {get_readable_file_size(task.listener.subsize)}"
                ac = len(task.listener.files_to_proceed)
                count = f"( {task.listener.proceed_count} / {ac or '?'} )"
            else:
                subsize = ""
                count = ""
            msg += f"\n┠ <b>ᴘʀᴏᴄᴇssᴇᴅ</b> → <i>{task.processed_bytes()}{subsize} ᴏғ {task.size()}</i>"
            if count:
                msg += f"\n┠ <b>ᴄᴏᴜɴᴛ:</b> → <b>{count}</b>"
            msg += f"\n┠ <b>sᴛᴀᴛᴜs</b> → <b>{tstatus}</b>"
            msg += f"\n┠ <b>sᴘᴇᴇᴅ</b> → <i>{task.speed()}</i>"
            msg += f"\n┠ <b>ᴛɪᴍᴇ</b> → <i>{task.eta()} of {get_readable_time(elapsed + get_raw_time(task.eta()))} ( {get_readable_time(elapsed)} )</i>"
            if tstatus == MirrorStatus.STATUS_DOWNLOAD and (
                task.listener.is_torrent or task.listener.is_qbit
            ):
                try:
                    msg += f"\n┠ <b>sᴇᴇᴅᴇʀs</b> → {task.seeders_num()} | <b>ʟᴇᴇᴄʜᴇʀs</b> → {task.leechers_num()}"
                except Exception:
                    pass
            # TODO: Add Connected Peers
        elif tstatus == MirrorStatus.STATUS_SEED:
            msg += f"\n┠ <b>sɪᴢᴇ</b> → <i>{task.size()}</i> | <b>ᴜᴘʟᴏᴀᴅᴇᴅ</b>  → <i>{task.uploaded_bytes()}</i>"
            msg += f"\n┠ <b>sᴛᴀᴛᴜs</b> → <b>{tstatus}</b>"
            msg += f"\n┠ <b>sᴘᴇᴇᴅ</b> → <i>{task.seed_speed()}</i>"
            msg += f"\n┠ <b>ʀᴀᴛɪᴏ</b> → <i>{task.ratio()}</i>"
            msg += f"\n┠ <b>ᴛɪᴍᴇ</b> → <i>{task.seeding_time()}</i> | <b>ᴇʟᴀᴘsᴇᴅ</b> → <i>{get_readable_time(elapsed)}</i>"
        else:
            msg += f"\n┠ <b>sɪᴢᴇ</b> → <i>{task.size()}</i>"
        msg += f"\n┠ <b>ᴇɴɢɪɴᴇ</b> → <i>{task.engine}</i>"
        msg += f"\n┠ <b>ɪɴ ᴍᴏᴅᴇ</b> → <i>{task.listener.mode[0]}</i>"
        msg += f"\n┠ <b>ᴏᴜᴛ ᴍᴏᴅᴇ</b> → <i>{task.listener.mode[1]}</i>"
        # TODO: Add Bt Sel
        from ..telegram_helper.bot_commands import BotCommands

        msg += f"\n<b>┖ sᴛᴏᴘ</b> → <i>/{BotCommands.CancelTaskCommand[1]}_{task.gid()}</i>\n\n"

    if len(msg) == 0:
        if status == "ᴀʟʟ":
            return None, None
        else:
            msg = f"ɴᴏ ᴀᴄᴛɪᴠᴇ {status} ᴛᴀsᴋs..!\n\n"

    msg += "🍳 <b>ʙᴏᴛ sᴛᴀᴛs</b>"
    buttons = ButtonMaker()
    if not is_user:
        buttons.data_button("📜 ᴛsᴛᴀᴛs", f"status {sid} ov", position="header")
    if len(tasks) > STATUS_LIMIT:
        msg += f"<b>ᴘᴀɢᴇ:</b> {page_no}/{pages} | <b>ᴛᴀsᴋ:</b> {tasks_no} | <b>sᴛᴇᴘ:</b> {page_step}\n"
        buttons.data_button("<<", f"status {sid} pre", position="header")
        buttons.data_button(">>", f"status {sid} nex", position="header")
        if tasks_no > 30:
            for i in [1, 2, 4, 6, 8, 10, 15]:
                buttons.data_button(i, f"status {sid} ps {i}", position="footer")
    if status != "ᴀʟʟ" or tasks_no > 20:
        for label, status_value in list(STATUSES.items()):
            if status_value != status:
                buttons.data_button(label, f"status {sid} st {status_value}")
    buttons.data_button("♻️ ʀᴇғʀᴇsʜ", f"status {sid} ref", position="header")
    button = buttons.build_menu(8)
    msg += f"\n┟ <b>ᴄᴘᴜ</b> → {cpu_percent()}% | <b>ғ</b> → {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)} [{round(100 - disk_usage(DOWNLOAD_DIR).percent, 1)}%]"
    msg += f"\n┖ <b>ʀᴀᴍ</b> → {virtual_memory().percent}% | <b>ᴜᴘ</b> → {get_readable_time(time() - bot_start_time)}"
    return msg, button
