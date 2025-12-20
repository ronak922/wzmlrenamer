from asyncio import TimeoutError, gather
from contextlib import suppress
from inspect import iscoroutinefunction
from pathlib import Path

from aioaria2 import Aria2WebsocketClient
from aiohttp import ClientError
from aioqbt.client import create_client
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .. import LOGGER, aria2_options
from .config_manager import Config


def wrap_with_retry(obj, max_retries=3):
    for attr_name in dir(obj):
        if attr_name.startswith("_"):
            continue

        attr = getattr(obj, attr_name)
        if iscoroutinefunction(attr):
            retry_policy = retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=1, min=1, max=5),
                retry=retry_if_exception_type(
                    (ClientError, TimeoutError, RuntimeError)
                ),
            )
            wrapped = retry_policy(attr)
            setattr(obj, attr_name, wrapped)
    return obj


# bot/core/torrent_manager.py

class TorrentManager:
    @classmethod
    async def initiate(cls):
        return

    @classmethod
    async def close_all(cls):
        return

    @classmethod
    async def remove_all(cls):
        return

    @classmethod
    async def pause_all(cls):
        return

    @classmethod
    async def overall_speed(cls):
        return 0, 0

    @classmethod
    async def aria2_remove(cls, download):
        return

    @classmethod
    async def change_aria2_option(cls, key, value):
        return


def aria2_name(download_info):
    if "bittorrent" in download_info and download_info["bittorrent"].get("info"):
        return download_info["bittorrent"]["info"]["name"]
    elif download_info.get("files"):
        if download_info["files"][0]["path"].startswith("[METADATA]"):
            return download_info["files"][0]["path"]
        file_path = download_info["files"][0]["path"]
        dir_path = download_info["dir"]
        if file_path.startswith(dir_path):
            return Path(file_path[len(dir_path) + 1 :]).parts[0]
        else:
            return ""
    else:
        return ""


def is_metadata(download_info):
    return any(
        f["path"].startswith("[METADATA]") for f in download_info.get("files", [])
    )
