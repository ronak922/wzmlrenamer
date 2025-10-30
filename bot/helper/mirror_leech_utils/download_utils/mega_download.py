from secrets import token_hex
from aiofiles.os import makedirs

from mega import MegaApi

from .... import LOGGER, task_dict, task_dict_lock
from ....core.config_manager import Config
from ...ext_utils.links_utils import get_mega_link_type
from ...ext_utils.bot_utils import sync_to_async

from ...ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
    limit_checker,
)
from ...mirror_leech_utils.status_utils.mega_dl_status import MegaDownloadStatus
from ...mirror_leech_utils.status_utils.queue_status import QueueStatus
from ...telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    send_message,
    send_status_message,
)
from ...listeners.mega_listener import (
    MegaAppListener,
    AsyncMega,
)


async def add_mega_download(listener, path):
    async_api = AsyncMega()
    async_api.api = api = MegaApi(None, None, None, "WZML-X")
    folder_api = None

    mega_listener = MegaAppListener(async_api.continue_event, listener)
    api.addListener(mega_listener)

    if (MEGA_EMAIL := Config.MEGA_EMAIL) and (MEGA_PASSWORD := Config.MEGA_PASSWORD):
        await async_api.login(MEGA_EMAIL, MEGA_PASSWORD)

    if get_mega_link_type(listener.link) == "file":
        await async_api.getPublicNode(listener.link)
        node = mega_listener.public_node
    else:
        async_api.folder_api = folder_api = MegaApi(None, None, None, "WZML-X")
        folder_api.addListener(mega_listener)

        await async_api.run(folder_api.loginToFolder, listener.link)
        LOGGER.info(
            f"Folder login node: {mega_listener.node.getName()}, Type: {mega_listener.node.getType()}"
        )
        node = await sync_to_async(folder_api.authorizeNode, mega_listener.node)
        LOGGER.info(f"Authorized node: {node.getName()}, Type: {node.getType()}")

        children = api.getChildren(node)
        child_nodes = [children.get(i) for i in range(children.size())]
        LOGGER.info(f"Found children: {[child.getName() for child in child_nodes]}")

    if mega_listener.error:
        await listener.on_download_error(mega_listener.error)
        await async_api.logout()
        return

    listener.name = listener.name or node.getName()
    gid = token_hex(5)

    msg, button = await stop_duplicate_check(listener)
    if msg:
        await listener.on_download_error(msg, button)
        await async_api.logout()
        return

    listener.size = await sync_to_async(api.getSize, node)
    if limit_exceeded := await limit_checker(listener):
        await listener.on_download_error(limit_exceeded, is_limit=True)
        await async_api.logout()
        return

    added_to_queue, event = await check_running_tasks(listener)
    if added_to_queue:
        LOGGER.info(f"Added to Queue/Download: {listener.name}")
        async with task_dict_lock:
            task_dict[listener.mid] = QueueStatus(listener, gid, "Dl")
        await listener.on_download_start()
        if listener.multi <= 1:
            await send_status_message(listener.message)
        await event.wait()
        if listener.is_cancelled:
            await async_api.logout()
            return

    async with task_dict_lock:
        task_dict[listener.mid] = MegaDownloadStatus(listener, mega_listener, gid, "dl")

    if added_to_queue:
        LOGGER.info(f"Start Queued Download from Mega: {listener.name}")
    else:
        LOGGER.info(f"Download from Mega: {listener.name}")
        await listener.on_download_start()
        if listener.multi <= 1:
            await send_status_message(listener.message)

    await makedirs(path, exist_ok=True)
    await async_api.startDownload(node, path, listener.name, None, False, None)
    await async_api.logout()



from mega import MegaApi, MegaListener
import asyncio

class SimpleListener(MegaListener):
    def __init__(self):
        self.future = asyncio.get_event_loop().create_future()

    def onRequestFinish(self, api, request, error):
        if request.getType() == request.TYPE_LOGIN:
            if error and error.getErrorCode() != 0:
                self.future.set_exception(Exception(error.toString()))
            else:
                self.future.set_result(True)

async def login_to_mega(email, password):
    api = MegaApi("WZML-X")
    listener = SimpleListener()
    api.login(email, password, listener)
    await listener.future
    return api

async def rename_all(api: MegaApi, pattern: str):
    loop = asyncio.get_event_loop()
    root = api.getRootNode()
    nodes = api.getChildren(root)
    renamed = 0

    for i in range(nodes.size()):
        node = nodes.get(i)
        old_name = node.getName()
        new_name = f"{pattern}_{i+1}"
        try:
            await loop.run_in_executor(None, api.renameNode, node, new_name)
            renamed += 1
        except Exception as e:
            print(f"❌ Failed to rename {old_name}: {e}")
    return renamed

async def rename_mega_command(client, message):
    try:
        args = message.text.split(maxsplit=3)
        if len(args) < 3:
            return await send_message(
                message,
                "⚙️ Usage:\n`/rename_mega <email> <password> [rename_pattern]`\n\n"
                "Example:\n`/rename_mega test@gmail.com mypass RenamedFile`",
            )

        email, password = args[1], args[2]
        rename_pattern = args[3] if len(args) > 3 else "RenamedFile"

        msg = await send_message(message, "🔐 Logging into Mega account...")

        api = await login_to_mega(email, password)
        await msg.edit_text("✅ Logged in. Renaming files and folders...")

        renamed = await rename_all(api, rename_pattern)
        await msg.edit_text(f"✅ Renamed `{renamed}` items in account `{email}`.")

    except Exception as e:
        await send_message(message, f"❌ Error: {e}")
