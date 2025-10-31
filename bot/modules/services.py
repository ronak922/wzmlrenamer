from html import escape
from time import monotonic, time
from uuid import uuid4
from re import match
from pyrogram.filters import regex
from pyrogram.handlers import CallbackQueryHandler
from aiofiles import open as aiopen
from cloudscraper import create_scraper
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from pyrogram import Client, filters
from .. import LOGGER, user_data
from ..core.config_manager import Config
from ..core.tg_client import TgClient
from ..helper.ext_utils.bot_utils import new_task, update_user_ldata
from ..helper.ext_utils.links_utils import decode_slink
from ..helper.ext_utils.status_utils import get_readable_time
from ..helper.ext_utils.db_handler import database
from ..helper.languages import Language
from ..helper.telegram_helper.bot_commands import BotCommands
from ..helper.telegram_helper.button_build import ButtonMaker
from ..helper.telegram_helper.filters import CustomFilters
from ..helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    edit_reply_markup,
    send_file,
    send_message,
)
START_MSG = """<b>
⚡ ʜᴇʏ ʙᴜᴅᴅʏ ~

<blockquote>I ᴀᴍ ᴀɴ ᴀᴅᴠᴀɴᴄᴇᴅ ᴛᴇʟᴇɢʀᴀᴍ ʙᴏᴛ ᴛᴏ ʀᴇɴᴀᴍᴇʀ ᴍᴇɢᴀ ʟɪɴᴋs ᴡɪᴛʜ ᴇᴀsᴇ. ⚡
ᴍᴏᴅɪғɪᴇᴅ ʙʏ <a href="https://t.me/ProError">@ᴘʀᴏᴇʀʀᴏʀ</a></blockquote>
</b>
"""
START_BUTTON1 = "• ᴍᴀɪɴ ᴄʜᴀɴɴᴇʟ"
START_BUTTON2 = "• ᴏᴡɴᴇʀ •"


@new_task
async def start(_, message):
    userid = message.from_user.id
    buttons = ButtonMaker()
    buttons.url_button(START_BUTTON1, "https://t.me/bhookibhabhi")
    buttons.data_button("ᴀʙᴏᴜᴛ •", "about")
    buttons.url_button(START_BUTTON2, "https://t.me/dumpadmin")
    reply_markup = buttons.build_menu(2)

    await _.send_photo(
        chat_id=message.chat.id,
        photo="https://i.ibb.co/G4RHktPc/image.jpg",
        caption=START_MSG,
        reply_markup=reply_markup,
        message_effect_id=5104841245755180586

    )
    await delete_message(message)
    await database.set_pm_users(userid)



ABOUT_MSG = """<b>🤖 ᴍʏ ɴᴀᴍᴇ: {botname}
<blockquote expandable>» ᴀᴅᴠᴀɴᴄᴇ ғᴇᴀᴛᴜʀᴇs: <a href='https://telegra.ph/%F0%9D%99%8F%F0%9D%99%9A%F0%9D%99%A2%F0%9D%99%A4%F0%9D%99%A0%F0%9D%99%96%F0%9D%99%A9%F0%9D%99%9A--A-Powerful--Fully-Dynamic-Bot-Template--Built-for-Control-Speed--Scalability-09-22'>ᴄʟɪᴄᴋ ʜᴇʀᴇ</a>
» ʟᴀɴɢᴜᴀɢᴇ: <a href='https://docs.python.org/3/'>ᴘʏᴛʜᴏɴ 3</a>
» ꜱᴜᴘᴘᴏʀᴛ: <a href='https://t.me/teambhabhi'>ɢʀᴏᴜᴘ</a>
» ᴅᴇᴘʟᴏʏᴇᴅ ᴏɴ: <a href='https://t.me/AkshayCloud'>ᴠᴘs</a>
» ꜱᴏᴜʀᴄᴇ ᴄᴏᴅᴇ: @BotzGarage</a>
» ʀᴇᴘᴏʀᴛ ɪꜱꜱᴜᴇ: <a href="https://t.me/ProError">ɴᴏᴏʙ ᴅᴇᴠ ⚠️</a></blockquote></b>
"""


async def cb_about(client, callback_query):
    try:
        # Temporary "Please wait" loading
        await callback_query.message.edit_media(
            InputMediaPhoto(
                "https://i.ibb.co/9kCPFWrb/image.jpg",
                caption="⏳ ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ.."
            )
        )

        # Show the actual About message
        await callback_query.message.edit_media(
            InputMediaPhoto(
                "https://i.ibb.co/9kCPFWrb/image.jpg",
                caption=ABOUT_MSG.format(botname=client.me.first_name)
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("• ʙᴀᴄᴋ", callback_data="start_back"),
                    InlineKeyboardButton("ᴄʟᴏꜱᴇ •", callback_data="close")
                ]
            ])
        )
    except Exception as e:
        await callback_query.answer("❌ ᴇʀʀᴏʀ ɪɴ ᴀʙᴏᴜᴛ sᴇᴄᴛɪᴏɴ", show_alert=True)
        print(e)


TgClient.bot.add_handler(CallbackQueryHandler(cb_about, filters=regex("^about$")))


async def cb_back(client, query):
    lang = Language()
    buttons = ButtonMaker()
    buttons.url_button(lang.START_BUTTON1, "https://t.me/bhookibhabhi")
    buttons.data_button("ᴀʙᴏᴜᴛ •", "about")
    buttons.url_button(lang.START_BUTTON2, "https://t.me/dumpadmin")
    reply_markup = buttons.build_menu(2)

    await query.answer()
    await query.message.edit_media(
        InputMediaPhoto(
            "https://i.ibb.co/G4RHktPc/image.jpg",
            caption=lang.START_MSG.format(cmd=BotCommands.HelpCommand[0]),
        ),
        reply_markup=reply_markup,
    )


TgClient.bot.add_handler(CallbackQueryHandler(cb_back, filters=regex("^start_back$")))


async def cb_close(_, query):
    try:
        await query.message.delete()
    except:
        pass
TgClient.bot.add_handler(CallbackQueryHandler(cb_close, filters=regex("^close$")))

# @new_task
# async def start_cb(_, query):
#     user_id = query.from_user.id
#     input_token = query.data.split()[2]
#     data = user_data.get(user_id, {})

#     if input_token == "activated":
#         return await query.answer("Already Activated!", show_alert=True)
#     elif "VERIFY_TOKEN" not in data or data["VERIFY_TOKEN"] != input_token:
#         return await query.answer("Already Used, Generate New One", show_alert=True)

#     update_user_ldata(user_id, "VERIFY_TOKEN", str(uuid4()))
#     update_user_ldata(user_id, "VERIFY_TIME", time())
#     if Config.DATABASE_URL:
#         await database.update_user_data(user_id)
#     await query.answer("Activated Access Login Token!", show_alert=True)

#     kb = query.message.reply_markup.inline_keyboard[1:]
#     kb.insert(
#         0,
#         [InlineKeyboardButton("✅️ Activated ✅", callback_data="start pass activated")],
#     )
#     await edit_reply_markup(query.message, InlineKeyboardMarkup(kb))


# @new_task
# async def login(_, message):
#     if Config.LOGIN_PASS is None:
#         return await send_message(message, "<i>Login is not enabled !</i>")
#     elif len(message.command) > 1:
#         user_id = message.from_user.id
#         input_pass = message.command[1]

#         if user_data.get(user_id, {}).get("VERIFY_TOKEN", "") == Config.LOGIN_PASS:
#             return await send_message(
#                 message, "<b>Already Bot Login In!</b>\n\n<i>No Need to Login Again</i>"
#             )

#         if input_pass.casefold() != Config.LOGIN_PASS.casefold():
#             return await send_message(
#                 message, "<b>Wrong Password!</b>\n\n<i>Kindly check and try again</i>"
#             )

#         update_user_ldata(user_id, "VERIFY_TOKEN", Config.LOGIN_PASS)
#         if Config.DATABASE_URL:
#             await database.update_user_data(user_id)
#         return await send_message(
#             message, "<b>Bot Permanent Logged In!</b>\n\n<i>Now you can use the bot</i>"
#         )
#     else:
#         await send_message(
#             message, "<b>Bot Login Usage :</b>\n\n<code>/login [password]</code>"
#         )


# @new_task
# async def ping(_, message):
#     start_time = monotonic()
#     reply = await send_message(message, "<b>ᴘɪɴɢɪɴɢ..</b>")
#     end_time = monotonic()
#     await edit_message(
#         reply, f"<b>ᴘᴏɴɢ..!</b>\n <code>{int((end_time - start_time) * 1000)} ms</code>"
#     )


# @new_task
# async def log(_, message):
#     uid = message.from_user.id
#     buttons = ButtonMaker()
#     buttons.data_button("Log Disp", f"log {uid} disp")
#     buttons.data_button("Web Log", f"log {uid} web")
#     buttons.data_button("Close", f"log {uid} close")
#     await send_file(message, "log.txt", buttons=buttons.build_menu(2))


# @new_task
# async def log_cb(_, query):
#     data = query.data.split()
#     message = query.message
#     user_id = query.from_user.id
#     if user_id != int(data[1]):
#         await query.answer("Not Yours!", show_alert=True)
#     elif data[2] == "close":
#         await query.answer()
#         await delete_message(message, message.reply_to_message)
#     elif data[2] == "disp":
#         await query.answer("Fetching Log..")
#         async with aiopen("log.txt", "r") as f:
#             content = await f.read()

#         def parse(line):
#             parts = line.split("] [", 1)
#             return f"[{parts[1]}" if len(parts) > 1 else line

#         try:
#             res, total = [], 0
#             for line in reversed(content.splitlines()):
#                 line = parse(line)
#                 res.append(line)
#                 total += len(line) + 1
#                 if total > 3500:
#                     break

#             text = f"<b>Showing Last {len(res)} Lines from log.txt:</b> \n\n----------<b>START LOG</b>----------\n\n<blockquote expandable>{escape('\n'.join(reversed(res)))}</blockquote>\n----------<b>END LOG</b>----------"

#             btn = ButtonMaker()
#             btn.data_button("Close", f"log {user_id} close")
#             await send_message(message, text, btn.build_menu(1))
#             await edit_reply_markup(message, None)
#         except Exception as err:
#             LOGGER.error(f"TG Log Display : {str(err)}")
#     elif data[2] == "web":
#         boundary = "R1eFDeaC554BUkLF"
#         headers = {
#             "Content-Type": f"multipart/form-data; boundary=----WebKitFormBoundary{boundary}",
#             "Origin": "https://spaceb.in",
#             "Referer": "https://spaceb.in/",
#             "sec-ch-ua": '"Not-A.Brand";v="99", "Chromium";v="124"',
#             "sec-ch-ua-mobile": "?1",
#             "sec-ch-ua-platform": '"Android"',
#             "Sec-Fetch-Dest": "document",
#             "Sec-Fetch-Mode": "navigate",
#             "Sec-Fetch-Site": "same-origin",
#             "Sec-Fetch-User": "?1",
#             "Upgrade-Insecure-Requests": "1",
#             "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
#         }

#         async with aiopen("log.txt", "r") as f:
#             content = await f.read()

#         data = (
#             f"------WebKitFormBoundary{boundary}\r\n"
#             f'Content-Disposition: form-data; name="content"\r\n\r\n'
#             f"{content}\r\n"
#             f"------WebKitFormBoundary{boundary}--\r\n"
#         )

#         cget = create_scraper().request
#         resp = cget("POST", "https://spaceb.in/", headers=headers, data=data)
#         if resp.status_code == 200:
#             await query.answer("Generating..")
#             btn = ButtonMaker()
#             btn.url_button("📨 Web Paste (SB)", resp.url)
#             await edit_reply_markup(message, btn.build_menu(1))
#         else:
#             await query.answer("Web Paste Failed ! Check Logs", show_alert=True)
