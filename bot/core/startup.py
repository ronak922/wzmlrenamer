# ─── startup.py (torrent-free version) ───
from asyncio import create_subprocess_exec, create_subprocess_shell
from importlib import import_module
from os import environ, getenv, path as ospath
from aiofiles import open as aiopen
from aiofiles.os import makedirs, remove, path as aiopath
from aioshutil import rmtree
from sabnzbdapi.exception import APIResponseError

from .. import (
    LOGGER,
    auth_chats,
    drives_ids,
    drives_names,
    index_urls,
    shortener_dict,
    var_list,
    user_data,
    excluded_extensions,
    nzb_options,
    rss_dict,
    sabnzbd_client,
    sudo_users,
)
from ..helper.ext_utils.db_handler import database
from .config_manager import Config, BinConfig
from .tg_client import TgClient

# ───── Disable torrents permanently ─────
TORRENTS_ENABLED = False
TorrentManager = None

# ─── Placeholder torrent functions ───
async def update_qb_options():
    LOGGER.info("qBittorrent update skipped (torrents disabled)")

async def update_aria2_options():
    LOGGER.info("Aria2 update skipped (torrents disabled)")

# ─── NZB options ───
async def update_nzb_options():
    if Config.USENET_SERVERS:
        try:
            no = (await sabnzbd_client.get_config())["config"]["misc"]
            nzb_options.update(no)
        except Exception as e:
            LOGGER.error(f"Error in NZB Options: {e}")

# ─── Load settings from DB ───
async def load_settings():
    if not Config.DATABASE_URL:
        return

    for p in ["thumbnails", "tokens", "rclone"]:
        if await aiopath.exists(p):
            await rmtree(p, ignore_errors=True)

    await database.connect()
    if database.db is None:
        return

    BOT_ID = Config.BOT_TOKEN.split(":", 1)[0]

    # Load config from Python file or env
    try:
        settings = import_module("config")
        config_file = {k: v.strip() if isinstance(v, str) else v for k, v in vars(settings).items() if not k.startswith("__")}
    except ModuleNotFoundError:
        config_file = {}

    config_file.update({k: v.strip() if isinstance(v, str) else v for k, v in environ.items() if k in var_list})

    old_config = await database.db.settings.deployConfig.find_one({"_id": BOT_ID}, {"_id": 0})
    if old_config is None or old_config != config_file:
        await database.db.settings.deployConfig.replace_one({"_id": BOT_ID}, config_file, upsert=True)
        config_dict = await database.db.settings.config.find_one({"_id": BOT_ID}, {"_id": 0}) or {}
        config_dict.update(config_file)
        if config_dict:
            Config.load_dict(config_dict)
    else:
        config_dict = await database.db.settings.config.find_one({"_id": BOT_ID}, {"_id": 0})
        if config_dict:
            Config.load_dict(config_dict)

    # Load user files
    if pf_dict := await database.db.settings.files.find_one({"_id": BOT_ID}, {"_id": 0}):
        for key, value in pf_dict.items():
            if value:
                file_ = key.replace("__", ".")
                async with aiopen(file_, "wb+") as f:
                    await f.write(value)

    # Skip torrents completely
    if a2c_options := await database.db.settings.aria2c.find_one({"_id": BOT_ID}, {"_id": 0}):
        pass

    # Load NZB
    if nzb_opt := await database.db.settings.nzb.find_one({"_id": BOT_ID}, {"_id": 0}):
        if await aiopath.exists("sabnzbd/SABnzbd.ini.bak"):
            await remove("sabnzbd/SABnzbd.ini.bak")
        ((key, value),) = nzb_opt.items()
        file_ = key.replace("__", ".")
        async with aiopen(f"sabnzbd/{file_}", "wb+") as f:
            await f.write(value)
        LOGGER.info("Loaded Sabnzbd Data from MongoDB")

    # Load users
    if await database.db.users[BOT_ID].find_one():
        rows = database.db.users[BOT_ID].find({})
        async for row in rows:
            uid = row["_id"]
            del row["_id"]
            paths = {
                "THUMBNAIL": f"thumbnails/{uid}.jpg",
                "RCLONE_CONFIG": f"rclone/{uid}.conf",
                "TOKEN_PICKLE": f"tokens/{uid}.pickle",
                "USER_COOKIE_FILE": f"cookies/{uid}/cookies.txt",
            }
            async def save_file(file_path, content):
                dir_path = ospath.dirname(file_path)
                if not await aiopath.exists(dir_path):
                    await makedirs(dir_path)
                async with aiopen(file_path, "wb+") as f:
                    if isinstance(content, str):
                        content = content.encode("utf-8")
                    await f.write(content)
            for key, path in paths.items():
                if row.get(key):
                    await save_file(path, row[key])
                    row[key] = path
            user_data[uid] = row
        LOGGER.info("Users Data imported from MongoDB")

    # Load RSS
    if await database.db.rss[BOT_ID].find_one():
        rows = database.db.rss[BOT_ID].find({})
        async for row in rows:
            user_id = row["_id"]
            del row["_id"]
            rss_dict[user_id] = row
        LOGGER.info("RSS Data imported from MongoDB")

# ─── Save settings ───
async def save_settings():
    if database.db is None:
        return
    config_file = Config.get_all()
    await database.db.settings.config.update_one({"_id": TgClient.ID}, {"$set": config_file}, upsert=True)
    if await database.db.settings.nzb.find_one({"_id": TgClient.ID}) is None:
        async with aiopen("sabnzbd/SABnzbd.ini", "rb+") as pf:
            nzb_conf = await pf.read()
        await database.db.settings.nzb.update_one({"_id": TgClient.ID}, {"$set": {"SABnzbd__ini": nzb_conf}}, upsert=True)

# ─── Placeholder to avoid import errors ───
async def update_variables():
    # Validate split size
    if not Config.LEECH_SPLIT_SIZE or Config.LEECH_SPLIT_SIZE > TgClient.MAX_SPLIT_SIZE:
        Config.LEECH_SPLIT_SIZE = TgClient.MAX_SPLIT_SIZE

    # Premium-dependent features
    Config.HYBRID_LEECH = bool(Config.HYBRID_LEECH and TgClient.IS_PREMIUM_USER)
    Config.USER_TRANSMISSION = bool(Config.USER_TRANSMISSION and TgClient.IS_PREMIUM_USER)

    # Authorized chats
    if Config.AUTHORIZED_CHATS:
        for id_ in Config.AUTHORIZED_CHATS.split():
            chat_id, *threads = id_.split("|")
            auth_chats[int(chat_id)] = list(map(int, threads)) if threads else []

    # Sudo users
    if Config.SUDO_USERS:
        for uid in Config.SUDO_USERS.split():
            sudo_users.append(int(uid.strip()))

    # Excluded extensions
    if Config.EXCLUDED_EXTENSIONS:
        for ext in Config.EXCLUDED_EXTENSIONS.split():
            excluded_extensions.append(ext.lstrip(".").strip().lower())

    # Drives
    if Config.GDRIVE_ID:
        drives_names.append("Main")
        drives_ids.append(Config.GDRIVE_ID)
        index_urls.append(Config.INDEX_URL)

    # IMDB template
    if not Config.IMDB_TEMPLATE:
        Config.IMDB_TEMPLATE = """<b>Title: </b> {title} [{year}]
<b>Also Known As:</b> {aka}
<b>Rating ⭐️:</b> <i>{rating}</i>
<b>Release Info: </b> <a href="{url_releaseinfo}">{release_date}</a>
<b>Genre: </b>{genres}
<b>IMDb URL:</b> {url}
<b>Language: </b>{languages}
<b>Country of Origin : </b> {countries}

<b>Story Line: </b><code>{plot}</code>

<a href="{url_cast}">Read More ...</a>"""

# ─── Load other configs ───
async def load_configurations():
    if not await aiopath.exists(".netrc"):
        async with aiopen(".netrc", "w"):
            pass

    await (await create_subprocess_shell(
        f"chmod 600 .netrc && cp .netrc /root/.netrc && chmod +x setpkgs.sh && ./setpkgs.sh {BinConfig.ARIA2_NAME} {BinConfig.SABNZBD_NAME}"
    )).wait()

    PORT = getenv("PORT") or Config.BASE_URL_PORT
    if PORT:
        await create_subprocess_shell(
            f"gunicorn -k uvicorn.workers.UvicornWorker -w 1 web.wserver:app --bind 0.0.0.0:{PORT}"
        )
        await create_subprocess_shell("python3 cron_boot.py")

    LOGGER.info("Torrent functionality is permanently disabled. Skipping all torrent setup.")
