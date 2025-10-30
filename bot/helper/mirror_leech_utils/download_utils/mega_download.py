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



from mega import MegaApi
from .... import LOGGER
from ...listeners.mega_listener import AsyncMega, MegaAppListener
from ...telegram_helper.message_utils import send_message
from ...ext_utils.bot_utils import sync_to_async
import os, time

# Store user prefixes temporarily in memory
USER_PREFIXES = {}


async def prefix_command(client, message):
    """Set custom rename prefix for a user."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await send_message(
            message,
            "⚙️ ᴜsᴀɢᴇ:\n/prefix <ᴘʀᴇꜰɪx>\n\n📘 ᴇxᴀᴍᴘʟᴇ:\n/prefix @BhookiBhabhi"
        )

    prefix = args[1].strip()
    user_id = message.from_user.id
    USER_PREFIXES[user_id] = prefix

    await send_message(
        message,
        f"✅ ᴘʀᴇꜰɪx sᴇᴛ ᴛᴏ: {prefix}\n"
        f"⚡ ɴᴏᴡ ʏᴏᴜ ᴄᴀɴ ᴜsᴇ /rename_mega ᴡɪᴛʜᴏᴜᴛ ᴛʏᴘɪɴɢ ɪᴛ."
    )


async def rename_mega_command(client, message):
    try:
        args = message.text.split(maxsplit=3)
        if len(args) < 3:
            return await send_message(
                message,
                "⚙️ ᴜsᴀɢᴇ:\n/rename_mega <email> <password> [prefix]\n\n"
                "📘 ᴇxᴀᴍᴘʟᴇ:\n/rename_mega test@gmail.com mypass RenamedFile"
            )

        email, password = args[1], args[2]

        # Use either command argument or saved user prefix
        user_id = message.from_user.id
        rename_prefix = None
        if len(args) > 3:
            rename_prefix = args[3]
        elif user_id in USER_PREFIXES:
            rename_prefix = USER_PREFIXES[user_id]

        msg = await send_message(message, "<b>🔐 ʟᴏɢɢɪɴɢ ɪɴᴛᴏ ᴍᴇɢᴀ ᴀᴄᴄᴏᴜɴᴛ...</b>")

        start_time = time.time()

        # Create isolated Mega session per user
        async_api = AsyncMega()
        async_api.api = api = MegaApi(None, None, None, "PRO_ERROR_RENAME")
        mega_listener = MegaAppListener(async_api.continue_event, None)
        api.addListener(mega_listener)

        try:
            await async_api.login(email, password)
            await msg.edit_text("<b>✅ ʟᴏɢɢᴇᴅ ɪɴ sᴜᴄᴄᴇssꜰᴜʟʟʏ.\n📂 ꜰᴇᴛᴄʜɪɴɢ ꜱᴛʀᴜᴄᴛᴜʀᴇ...</b>")
        except Exception as e:
            return await msg.edit_text(f"<b>❌ ʟᴏɢɪɴ ꜰᴀɪʟᴇᴅ:\n{e}</b>")

        root = api.getRootNode()

        async def traverse_and_rename(node, level=0, counter=[0]):
            children = api.getChildren(node)
            if not children or children.size() == 0:
                return []

            results = []
            for i in range(children.size()):
                item = children.get(i)
                name = item.getName()
                is_folder = item.isFolder()
                indent = "  " * level
                results.append(f"{indent}📁 {name}" if is_folder else f"{indent}📄 {name}")

                # Rename files (preserve extension)
                if rename_prefix and not is_folder:
                    counter[0] += 1
                    base, ext = os.path.splitext(name)
                    new_name = f"{rename_prefix}_{counter[0]}{ext}" if ext else f"{rename_prefix}_{counter[0]}"
                    try:
                        await sync_to_async(api.renameNode, item, new_name)
                        LOGGER.info(f"Renamed: {name} → {new_name}")
                    except Exception as e:
                        LOGGER.error(f"❌ Rename failed for {name}: {e}")

                if is_folder:
                    sub_results = await traverse_and_rename(item, level + 1, counter)
                    results.extend(sub_results)
            return results

        results = await traverse_and_rename(root)
        total_items = len(results)
        time_taken = round(time.time() - start_time, 2)

        if not results:
            await msg.edit_text("⚠️ ɴᴏ ꜰɪʟᴇꜱ ᴏʀ ꜰᴏʟᴅᴇʀꜱ ꜰᴏᴜɴᴅ.")
        elif not rename_prefix:
            display = "\n".join(results[:30])
            more = f"\n\n...ᴀɴᴅ ᴍᴏʀᴇ ({total_items} ᴛᴏᴛᴀʟ)" if total_items > 30 else ""
            await msg.edit_text(
                f"✅ ʟᴏɢɪɴ: {email}\n📦 ɪᴛᴇᴍꜱ: {total_items}\n\n{display}{more}"
            )
        else:
            await msg.edit_text(
                f"<b>✅ ʀᴇɴᴀᴍᴇᴅ {total_items} ɪᴛᴇᴍꜱ ʀᴇᴄᴜʀꜱɪᴠᴇʟʏ\n"
                f"🆔 {email}\n"
                f"🔤 ᴘʀᴇꜰɪx: {rename_prefix}\n"
                f"⏱️ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ɪɴ {time_taken} sᴇᴄᴏɴᴅꜱ</b>"
            )

        await async_api.logout()

    except Exception as e:
        LOGGER.error(f"Error in rename_mega_command: {e}")
        await send_message(message, f"❌ ᴇʀʀᴏʀ: {e}")
