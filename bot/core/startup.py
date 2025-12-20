from asyncio import create_subprocess_exec, create_subprocess_shell
from importlib import import_module
from os import environ, getenv, path as ospath

from aiofiles import open as aiopen
from aiofiles.os import makedirs, remove, path as aiopath
# from aioshutil import rmtree

from .. import (
    LOGGER,
    aria2_options,
    drives_ids,
    drives_names,
    index_urls,
    shortener_dict,
    var_list,
    user_data,
    excluded_extensions,
)
from ..helper.ext_utils.db_handler import database
from .config_manager import Config, BinConfig
from .tg_client import TgClient

# ─────────────────────────────
# Torrent support removed
# ─────────────────────────────

async def load_configurations():
    if not await aiopath.exists(".netrc"):
        async with aiopen(".netrc", "w"):
            pass

    await (
        await create_subprocess_shell(
            f"chmod 600 .netrc && cp .netrc /root/.netrc && chmod +x setpkgs.sh && ./setpkgs.sh {BinConfig.ARIA2_NAME} {BinConfig.SABNZBD_NAME}"
        )
    ).wait()

    PORT = getenv("PORT", "") or Config.BASE_URL_PORT
    if PORT:
        await create_subprocess_shell(
            f"gunicorn -k uvicorn.workers.UvicornWorker -w 1 web.wserver:app --bind 0.0.0.0:{PORT}"
        )
        await create_subprocess_shell("python3 cron_boot.py")

    # # Extract cfg.zip
    # if await aiopath.exists("cfg.zip"):
    #     if await aiopath.exists("/JDownloader/cfg"):
    #         await rmtree("/JDownloader/cfg", ignore_errors=True)
    #     await (await create_subprocess_exec("7z", "x", "cfg.zip", "-o/JDownloader")).wait()

    # # Extract accounts.zip
    # if await aiopath.exists("accounts.zip"):
    #     if await aiopath.exists("accounts"):
    #         await rmtree("accounts")
    #     await (
    #         await create_subprocess_exec(
    #             "7z", "x", "-o.", "-aoa", "accounts.zip", "accounts/*.json"
    #         )
    #     ).wait()
    #     await (await create_subprocess_exec("chmod", "-R", "777", "accounts")).wait()
    #     await remove("accounts.zip")

    if not await aiopath.exists("accounts"):
        Config.USE_SERVICE_ACCOUNTS = False

    # ─────────────────────────────
    # Torrent initialization skipped
    # ─────────────────────────────
    LOGGER.info("Torrents are disabled. Skipping qBittorrent & Aria2 setup.")

