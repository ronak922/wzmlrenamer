from importlib import import_module

from aiofiles import open as aiopen
from aiofiles.os import path as aiopath
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
from pymongo.server_api import ServerApi
from datetime import datetime, timedelta
from ... import LOGGER, qbit_options, rss_dict, user_data
from ...core.config_manager import Config
from ...core.tg_client import TgClient


class DbManager:
    def __init__(self):
        self._return = True
        self._conn = None
        self.db = None

    async def connect(self):
        try:
            if self._conn is not None:
                await self._conn.close()
            self._conn = AsyncIOMotorClient(
                Config.DATABASE_URL, server_api=ServerApi("1")
            )
            self.db = self._conn.wzmlx
            self._return = False
        except PyMongoError as e:
            LOGGER.error(f"Error in DB connection: {e}")
            self.db = None
            self._return = True
            self._conn = None

    async def disconnect(self):
        self._return = True
        if self._conn is not None:
            await self._conn.close()
        self._conn = None

    async def update_deploy_config(self):
        if self._return:
            return
        settings = import_module("config")
        config_file = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in vars(settings).items()
            if not key.startswith("__")
        }
        await self.db.settings.deployConfig.replace_one(
            {"_id": TgClient.ID}, config_file, upsert=True
        )

    async def update_config(self, dict_):
        if self._return:
            return
        await self.db.settings.config.update_one(
            {"_id": TgClient.ID}, {"$set": dict_}, upsert=True
        )

    async def update_aria2(self, key, value):
        if self._return:
            return
        await self.db.settings.aria2c.update_one(
            {"_id": TgClient.ID}, {"$set": {key: value}}, upsert=True
        )

    async def update_qbittorrent(self, key, value):
        if self._return:
            return
        await self.db.settings.qbittorrent.update_one(
            {"_id": TgClient.ID}, {"$set": {key: value}}, upsert=True
        )

    async def save_qbit_settings(self):
        if self._return:
            return
        await self.db.settings.qbittorrent.update_one(
            {"_id": TgClient.ID}, {"$set": qbit_options}, upsert=True
        )

    async def update_private_file(self, path):
        if self._return:
            return
        db_path = path.replace(".", "__")
        if await aiopath.exists(path):
            async with aiopen(path, "rb+") as pf:
                pf_bin = await pf.read()
            await self.db.settings.files.update_one(
                {"_id": TgClient.ID}, {"$set": {db_path: pf_bin}}, upsert=True
            )
            if path == "config.py":
                await self.update_deploy_config()
        else:
            await self.db.settings.files.update_one(
                {"_id": TgClient.ID}, {"$unset": {db_path: ""}}, upsert=True
            )

    async def update_nzb_config(self):
        if self._return:
            return
        async with aiopen("sabnzbd/SABnzbd.ini", "rb+") as pf:
            nzb_conf = await pf.read()
        await self.db.settings.nzb.replace_one(
            {"_id": TgClient.ID}, {"SABnzbd__ini": nzb_conf}, upsert=True
        )

    async def update_user_data(self, user_id):
        if self._return:
            return
        data = user_data.get(user_id, {})
        data = data.copy()
        for key in ("THUMBNAIL", "RCLONE_CONFIG", "TOKEN_PICKLE", "USER_COOKIE_FILE"):
            data.pop(key, None)
        pipeline = [
            {
                "$replaceRoot": {
                    "newRoot": {
                        "$mergeObjects": [
                            data,
                            {
                                "$arrayToObject": {
                                    "$filter": {
                                        "input": {"$objectToArray": "$$ROOT"},
                                        "as": "field",
                                        "cond": {
                                            "$in": [
                                                "$$field.k",
                                                [
                                                    "THUMBNAIL",
                                                    "RCLONE_CONFIG",
                                                    "TOKEN_PICKLE",
                                                    "USER_COOKIE_FILE",
                                                ],
                                            ]
                                        },
                                    }
                                }
                            },
                        ]
                    }
                }
            }
        ]
        await self.db.users[TgClient.ID].update_one(
            {"_id": user_id}, pipeline, upsert=True
        )

    async def update_user_doc(self, user_id, key, path=""):
        if self._return:
            return
        if path:
            async with aiopen(path, "rb+") as doc:
                doc_bin = await doc.read()
            await self.db.users[TgClient.ID].update_one(
                {"_id": user_id}, {"$set": {key: doc_bin}}, upsert=True
            )
        else:
            await self.db.users[TgClient.ID].update_one(
                {"_id": user_id}, {"$unset": {key: ""}}, upsert=True
            )

    async def rss_update_all(self):
        if self._return:
            return
        for user_id in list(rss_dict.keys()):
            await self.db.rss[TgClient.ID].replace_one(
                {"_id": user_id}, rss_dict[user_id], upsert=True
            )

    async def rss_update(self, user_id):
        if self._return:
            return
        await self.db.rss[TgClient.ID].replace_one(
            {"_id": user_id}, rss_dict[user_id], upsert=True
        )

    async def rss_delete(self, user_id):
        if self._return:
            return
        await self.db.rss[TgClient.ID].delete_one({"_id": user_id})

    async def add_incomplete_task(self, cid, link, tag):
        if self._return:
            return
        await self.db.tasks[TgClient.ID].insert_one(
            {"_id": link, "cid": cid, "tag": tag}
        )

    async def get_pm_uids(self):
        if self._return:
            return
        return [doc["_id"] async for doc in self.db.pm_users[TgClient.ID].find({})]

    async def set_pm_users(self, user_id):
        if self._return:
            return
        if not bool(await self.db.pm_users[TgClient.ID].find_one({"_id": user_id})):
            await self.db.pm_users[TgClient.ID].insert_one({"_id": user_id})
            LOGGER.info(f"New PM User Added : {user_id}")

    async def rm_pm_user(self, user_id):
        if self._return:
            return
        await self.db.pm_users[TgClient.ID].delete_one({"_id": user_id})

    async def rm_complete_task(self, link):
        if self._return:
            return
        await self.db.tasks[TgClient.ID].delete_one({"_id": link})

    async def get_incomplete_tasks(self):
        notifier_dict = {}
        if self._return:
            return notifier_dict
        if await self.db.tasks[TgClient.ID].find_one():
            rows = self.db.tasks[TgClient.ID].find({})
            async for row in rows:
                if row["cid"] in list(notifier_dict.keys()):
                    if row["tag"] in list(notifier_dict[row["cid"]]):
                        notifier_dict[row["cid"]][row["tag"]].append(row["_id"])
                    else:
                        notifier_dict[row["cid"]][row["tag"]] = [row["_id"]]
                else:
                    notifier_dict[row["cid"]] = {row["tag"]: [row["_id"]]}
        await self.db.tasks[TgClient.ID].drop()
        return notifier_dict

    async def trunc_table(self, name):
        if self._return:
            return
        await self.db[name][TgClient.ID].drop()

    async def set_user_prefix(self, user_id: int, prefix: str):
        await self.db.prefix.update_one({"_id": user_id}, {"$set": {"prefix": prefix}}, upsert=True)

    async def get_user_prefix(self, user_id: int):
        doc = await self.db.prefix.find_one({"_id": user_id})
        return doc.get("prefix") if doc else None

    async def set_user_folder_state(self, user_id: int, enabled: bool):
        await self.db.folder_state.update_one({"_id": user_id}, {"$set": {"enabled": enabled}}, upsert=True)

    async def get_user_folder_state(self, user_id: int) -> bool:
        doc = await self.db.folder_state.find_one({"_id": user_id})
        return doc.get("enabled", False) if doc else False
    
    async def set_user_swap_state(self, user_id: int, state: bool):
        if self._return:
            return
        await self.db.swap_state.update_one(
            {"_id": user_id}, {"$set": {"swap_mode": state}}, upsert=True
        )

    async def get_user_swap_state(self, user_id: int) -> bool:
        if self._return:
            return False
        doc = await self.db.swap_state.find_one({"_id": user_id})
        return doc.get("swap_mode", False) if doc else False


    # ─────────────────────────────
    # 💎 Premium System
    # ─────────────────────────────
    async def set_user_premium(self, user_id: int, days: int):
        """Add or extend premium for a user."""
        if self._return:
            return
        expiry = datetime.utcnow() + timedelta(days=days)
        await self.db.premium.update_one(
            {"_id": user_id},
            {"$set": {"is_premium": True, "expiry": expiry.timestamp()}},
            upsert=True,
        )

    async def remove_user_premium(self, user_id: int):
        """Remove premium status."""
        if self._return:
            return
        await self.db.premium.update_one(
            {"_id": user_id},
            {"$set": {"is_premium": False, "expiry": None}},
            upsert=True,
        )

    async def is_user_premium(self, user_id: int) -> bool:
        """Check if user is currently premium."""
        if self._return:
            return False
        doc = await self.db.premium.find_one({"_id": user_id})
        if not doc or not doc.get("is_premium"):
            return False

        expiry = doc.get("expiry")
        if not expiry:
            return False

        now = datetime.utcnow().timestamp()
        if now > expiry:
            # Expired → revoke premium
            await self.remove_user_premium(user_id)
            return False

        return True

    async def get_premium_info(self, user_id: int) -> str:
        """Return formatted premium info (for debugging or admin view)."""
        if self._return:
            return "❌ DB not connected"
        doc = await self.db.premium.find_one({"_id": user_id})
        if not doc or not doc.get("is_premium"):
            return f"🆓 User <code>{user_id}</code> is not premium."
        expiry_dt = datetime.utcfromtimestamp(doc['expiry'])
        return f"💎 User <code>{user_id}</code> is premium until <b>{expiry_dt:%d-%b-%Y %H:%M UTC}</b>"

database = DbManager()
