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
        f"⚡ ɴᴏᴡ ʏᴏᴜ ᴄᴀɴ ᴜsᴇ /rename ᴡɪᴛʜᴏᴜᴛ ᴛʏᴘɪɴɢ ɪᴛ."
    )


async def rename_mega_command(client, message):
    try:
        args = message.text.split(maxsplit=3)
        if len(args) < 3:
            return await send_message(
                message,
                "⚙️ ᴜsᴀɢᴇ:\n/rename <email> <password> [prefix]\n\n"
                "📘 ᴇxᴀᴍᴘʟᴇ:\n/rename test@gmail.com mypass RenamedFile"
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
