# bot/core/torrent_manager.py
from pathlib import Path

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
