import db
import aiohttp
import logging
import asyncio
import aiofiles
import os
import re
import tempfile
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

setting = db.get_config()

bot = Bot(setting['bot_token'])
admin = int(setting['admin_id'])
WG_CONFIG_FILE = setting['wg_config_file']

dp = Dispatcher(bot)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=pytz.UTC)
scheduler.start()

main_menu_markup = InlineKeyboardMarkup(row_width=1).add(
    InlineKeyboardButton("Добавить пользователя", callback_data="add_user"),
    InlineKeyboardButton("Получить конфигурацию пользователя", callback_data="get_config"),
    InlineKeyboardButton("Список клиентов", callback_data="list_users")
)

user_main_messages = {}

def get_ipv6_subnet():
    try:
        with open(WG_CONFIG_FILE, 'r') as f:
            in_interface = False
            for line in f:
                line = line.strip()
                if line.startswith('[Interface]'):
                    in_interface = True
                    continue
                if in_interface:
                    if line.startswith('Address'):
                        addresses = line.split('=')[1].strip().split(',')
                        for addr in addresses:
                            addr = addr.strip()
                            if ':' in addr:
                                parts = addr.split('/')
                                if len(parts) == 2:
                                    ip, mask = parts
                                    prefix = re.sub(r'::[0-9a-fA-F]+$', '::', ip)
                                    return f"{prefix}/64"
                        return None
                    elif line.startswith('['):
                        break
    except Exception as e:
        logger.error(f"Ошибка при чтении файла конфигурации AmneziaWG: {e}")
        return None

def is_user_blocked(username):
    try:
        with open(WG_CONFIG_FILE, 'r') as f:
            config = f.read()

        pattern = rf'(# BEGIN_PEER {username}\n)(.*?\n)(# END_PEER {username})'
        match = re.search(pattern, config, re.DOTALL)
        if match:
            peer_block = match.group(2)
            lines = peer_block.strip().split('\n')
            if all(line.strip().startswith('#') or line.strip() == '' for line in lines):
                logger.debug(f"User {username} is blocked.")
                return True
            else:
                logger.debug(f"User {username} is active.")
                return False
        else:
            logger.debug(f"User {username} not found.")
            return False

    except Exception as e:
        logger.error(f"Ошибка при проверке статуса блокировки пользователя {username}: {e}")
        return False

async def block_user(username):
    try:
        async with aiofiles.open(WG_CONFIG_FILE, 'r') as f:
            config = await f.read()

        pattern = rf'(# BEGIN_PEER {username}\n)(.*?)(# END_PEER {username})'
        match = re.search(pattern, config, re.DOTALL)
        if match:
            start = match.group(1)
            peer_block = match.group(2)
            end = match.group(3)
            lines = peer_block.splitlines(keepends=True)
            commented_lines = [f'# {line}' if not line.strip().startswith('#') else line for line in lines]
            commented_block = ''.join(commented_lines)
            new_block = f'{start}{commented_block}{end}'
            config = config.replace(match.group(0), new_block)
        else:
            logger.error(f"Блок [Peer] для пользователя {username} не найден.")
            return False

        async with aiofiles.open(WG_CONFIG_FILE, 'w') as f:
            await f.write(config)

        success = await restart_wireguard()
        if not success:
            logger.error("Не удалось применить изменения конфигурации.")
            return False

        return True
    except Exception as e:
        logger.error(f"Ошибка при блокировке пользователя {username}: {e}")
        return False

async def unblock_user(username):
    try:
        async with aiofiles.open(WG_CONFIG_FILE, 'r') as f:
            config = await f.read()

        pattern = rf'(# BEGIN_PEER {username}\n)(.*?)(# END_PEER {username})'
        match = re.search(pattern, config, re.DOTALL)
        if match:
            start = match.group(1)
            peer_block = match.group(2)
            end = match.group(3)
            lines = peer_block.splitlines(keepends=True)
            uncommented_lines = [line.lstrip('# ').rstrip('\n') + '\n' for line in lines]
            uncommented_block = ''.join(uncommented_lines)
            new_block = f'{start}{uncommented_block}{end}'
            config = config.replace(match.group(0), new_block)
        else:
            logger.error(f"Закомментированный блок [Peer] для пользователя {username} не найден.")
            return False

        async with aiofiles.open(WG_CONFIG_FILE, 'w') as f:
            await f.write(config)

        success = await restart_wireguard()
        if not success:
            logger.error("Не удалось применить изменения конфигурации.")
            return False

        return True
    except Exception as e:
        logger.error(f"Ошибка при разблокировке пользователя {username}: {e}")
        return False

async def restart_wireguard():
    try:
        interface_name = os.path.basename(WG_CONFIG_FILE).split('.')[0]

        process_strip = await asyncio.create_subprocess_shell(
            f'wg-quick strip {interface_name}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_strip, stderr_strip = await process_strip.communicate()
        if process_strip.returncode != 0:
            logger.error(f"Ошибка при выполнении 'wg-quick strip {interface_name}': {stderr_strip.decode().strip()}")
            return False

        with tempfile.NamedTemporaryFile(delete=False) as temp_config:
            temp_config.write(stdout_strip)
            temp_config_path = temp_config.name

        process_syncconf = await asyncio.create_subprocess_shell(
            f'wg syncconf {interface_name} {temp_config_path}',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_syncconf, stderr_syncconf = await process_syncconf.communicate()
        if process_syncconf.returncode != 0:
            logger.error(f"Ошибка при выполнении 'wg syncconf {interface_name}': {stderr_syncconf.decode().strip()}")
            os.unlink(temp_config_path)
            return False

        os.unlink(temp_config_path)
        return True
    except Exception as e:
        logger.error(f"Ошибка при перезапуске AmneziaWG: {e}")
        return False

async def delete_message_after_delay(chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение {message_id} в чате {chat_id}: {e}")

@dp.message_handler(commands=['start', 'help'])
async def help_command_handler(message: types.Message):
    if message.chat.id == admin:
        sent_message = await message.answer("Выберите действие:", reply_markup=main_menu_markup)
        user_main_messages[admin] = (sent_message.chat.id, sent_message.message_id)
        try:
            await bot.pin_chat_message(chat_id=message.chat.id, message_id=sent_message.message_id, disable_notification=True)
        except Exception as e:
            logger.error(f"Не удалось закрепить сообщение: {e}")
    else:
        await message.answer("У вас нет доступа к этому боту.")

@dp.message_handler()
async def handle_messages(message: types.Message):
    if message.chat.id != admin:
        await message.answer("У вас нет доступа к этому боту.")
        return

    if user_main_messages.get('waiting_for_user_name'):
        user_name = message.text.strip()

        if not all(c.isalnum() or c in "-_" for c in user_name):
            await message.reply("Имя пользователя может содержать только буквы, цифры, дефисы и подчёркивания.")
            asyncio.create_task(delete_message_after_delay(message.chat.id, message.message_id, delay=5))
            return

        user_main_messages['client_name'] = user_name
        user_main_messages['waiting_for_user_name'] = False

        ipv6_subnet = get_ipv6_subnet()
        logger.info(f"IPv6 подсеть: {ipv6_subnet}")

        if ipv6_subnet:
            connect_buttons = [
                InlineKeyboardButton("С IPv6", callback_data=f'connect_{user_name}_ipv6'),
                InlineKeyboardButton("Без IPv6", callback_data=f'connect_{user_name}_noipv6'),
                InlineKeyboardButton("Домой", callback_data="home")
            ]
            connect_markup = InlineKeyboardMarkup(row_width=1).add(*connect_buttons)

            main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))

            if main_chat_id and main_message_id:
                await bot.edit_message_text(
                    chat_id=main_chat_id,
                    message_id=main_message_id,
                    text=f"Выберите тип подключения для пользователя **{user_name}**:",
                    parse_mode="Markdown",
                    reply_markup=connect_markup
                )
            else:
                logger.error("Главное сообщение не найдено для администратора.")
                await message.answer("Ошибка: главное сообщение не найдено.")
        else:
            user_main_messages['ipv6'] = 'noipv6'

            duration_buttons = [
                InlineKeyboardButton("1 час", callback_data=f"duration_1h_{user_name}_noipv6"),
                InlineKeyboardButton("1 день", callback_data=f"duration_1d_{user_name}_noipv6"),
                InlineKeyboardButton("1 неделя", callback_data=f"duration_1w_{user_name}_noipv6"),
                InlineKeyboardButton("1 месяц", callback_data=f"duration_1m_{user_name}_noipv6"),
                InlineKeyboardButton("Без ограничений", callback_data=f"duration_unlimited_{user_name}_noipv6"),
                InlineKeyboardButton("Домой", callback_data="home")
            ]
            duration_markup = InlineKeyboardMarkup(row_width=1).add(*duration_buttons)

            main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))

            if main_chat_id and main_message_id:
                await bot.edit_message_text(
                    chat_id=main_chat_id,
                    message_id=main_message_id,
                    text=f"Выберите время действия конфигурации для пользователя **{user_name}**:",
                    parse_mode="Markdown",
                    reply_markup=duration_markup
                )
            else:
                await message.answer("Ошибка: главное сообщение не найдено.")
    else:
        await message.reply("Неизвестная команда или действие.")

@dp.callback_query_handler(lambda c: c.data == "add_user")
async def prompt_for_user_name(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != admin:
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))
    if main_chat_id and main_message_id:
        await bot.edit_message_text(
            chat_id=main_chat_id,
            message_id=main_message_id,
            text="Введите имя пользователя для добавления:",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("Домой", callback_data="home")
            )
        )
        user_main_messages['waiting_for_user_name'] = True
    else:
        await callback_query.answer("Ошибка: главное сообщение не найдено.", show_alert=True)

    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('connect_'))
async def connect_user(callback: types.CallbackQuery):
    if callback.from_user.id != admin:
        await callback.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    try:
        _, client_name, ipv6_flag = callback.data.split('_', 2)
    except ValueError:
        await callback.answer("Неверный формат команды.", show_alert=True)
        return

    user_main_messages['client_name'] = client_name
    user_main_messages['ipv6'] = ipv6_flag

    duration_buttons = [
        InlineKeyboardButton("1 час", callback_data=f"duration_1h_{client_name}_{ipv6_flag}"),
        InlineKeyboardButton("1 день", callback_data=f"duration_1d_{client_name}_{ipv6_flag}"),
        InlineKeyboardButton("1 неделя", callback_data=f"duration_1w_{client_name}_{ipv6_flag}"),
        InlineKeyboardButton("1 месяц", callback_data=f"duration_1m_{client_name}_{ipv6_flag}"),
        InlineKeyboardButton("Без ограничений", callback_data=f"duration_unlimited_{client_name}_{ipv6_flag}"),
        InlineKeyboardButton("Домой", callback_data="home")
    ]
    duration_markup = InlineKeyboardMarkup(row_width=1).add(*duration_buttons)

    main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))
    if main_chat_id and main_message_id:
        await bot.edit_message_text(
            chat_id=main_chat_id,
            message_id=main_message_id,
            text="Выберите время действия конфигурации:",
            reply_markup=duration_markup
        )
    else:
        await callback.answer("Ошибка: главное сообщение не найдено.", show_alert=True)

    await callback.answer()

def parse_relative_time(time_str):
    now = datetime.now(pytz.UTC)
    delta = timedelta()

    parts = time_str.strip().split(',')
    for part in parts:
        part = part.strip()
        match = re.match(r'(\d+)\s+(day|hour|minute|second)s?', part)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            if unit == 'day':
                delta += timedelta(days=value)
            elif unit == 'hour':
                delta += timedelta(hours=value)
            elif unit == 'minute':
                delta += timedelta(minutes=value)
            elif unit == 'second':
                delta += timedelta(seconds=value)

    last_handshake_time = now - delta
    return last_handshake_time

@dp.callback_query_handler(lambda c: c.data.startswith('duration_'))
async def set_config_duration(callback: types.CallbackQuery):
    if callback.from_user.id != admin:
        await callback.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    parts = callback.data.split('_')
    duration_choice = parts[1]
    client_name = parts[2]
    ipv6_flag = parts[3] if len(parts) > 3 else 'noipv6'

    main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))
    if not main_chat_id or not main_message_id:
        await callback.answer("Ошибка: главное сообщение не найдено.", show_alert=True)
        return

    if duration_choice == '1h':
        duration = timedelta(hours=1)
    elif duration_choice == '1d':
        duration = timedelta(days=1)
    elif duration_choice == '1w':
        duration = timedelta(weeks=1)
    elif duration_choice == '1m':
        duration = timedelta(days=30)
    elif duration_choice == 'unlimited':
        duration = None
    else:
        await bot.send_message(admin, "Неверный выбор времени.", reply_markup=main_menu_markup)
        asyncio.create_task(delete_message_after_delay(admin, main_message_id, delay=2))
        return

    if ipv6_flag == 'ipv6':
        success = db.root_add(client_name, ipv6=True)
    else:
        success = db.root_add(client_name, ipv6=False)

    if success:
        try:
            with open(f'png/{client_name}.png', 'rb') as pfoto, open(f'conf/{client_name}.conf', 'rb') as file:
                sent_photo = await bot.send_photo(admin, pfoto)
                sent_doc = await bot.send_document(admin, file)
                asyncio.create_task(delete_message_after_delay(admin, sent_photo.message_id, delay=5))
                asyncio.create_task(delete_message_after_delay(admin, sent_doc.message_id, delay=5))
        except FileNotFoundError:
            confirmation_text = "Не удалось найти файлы конфигурации для указанного пользователя."
            sent_message = await bot.send_message(admin, confirmation_text, parse_mode="Markdown", reply_markup=main_menu_markup)
            asyncio.create_task(delete_message_after_delay(admin, sent_message.message_id, delay=2))
            return
        except Exception as e:
            confirmation_text = f"Произошла ошибка: {str(e)}"
            sent_message = await bot.send_message(admin, confirmation_text, parse_mode="Markdown", reply_markup=main_menu_markup)
            asyncio.create_task(delete_message_after_delay(admin, sent_message.message_id, delay=2))
            return

        if duration:
            expiration_time = datetime.now(pytz.UTC) + duration
            scheduler.add_job(
                deactivate_user,
                trigger=DateTrigger(run_date=expiration_time),
                args=[client_name],
                id=client_name
            )
            db.set_user_expiration(client_name, expiration_time)
            confirmation_text = f"Пользователь **{client_name}** добавлен. Конфигурация истечет через **{duration_choice}**."
        else:
            db.set_user_expiration(client_name, None)
            confirmation_text = f"Пользователь **{client_name}** добавлен с неограниченным временем действия."

        sent_confirmation = await bot.send_message(
            chat_id=admin,
            text=confirmation_text,
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_message_after_delay(admin, sent_confirmation.message_id, delay=2))
    else:
        confirmation_text = "Не удалось добавить пользователя."
        sent_confirmation = await bot.send_message(
            chat_id=admin,
            text=confirmation_text,
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_message_after_delay(admin, sent_confirmation.message_id, delay=2))

    await bot.edit_message_text(
        chat_id=main_chat_id,
        message_id=main_message_id,
        text="Выберите действие:",
        reply_markup=main_menu_markup
    )

    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('list_users'))
async def list_users_callback(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != admin:
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    clients = db.get_client_list()
    if not clients:
        await callback_query.answer("Список пользователей пуст.", show_alert=True)
        return

    active_clients = db.get_active_list()
    active_clients_dict = {}
    for client in active_clients:
        username = client[0]
        last_handshake = client[1]
        active_clients_dict[username] = last_handshake

    keyboard = InlineKeyboardMarkup(row_width=2)
    now = datetime.now(pytz.UTC)
    for client in clients:
        username = client[0]
        last_handshake_str = active_clients_dict.get(username)

        if last_handshake_str:
            last_handshake = parse_relative_time(last_handshake_str)
        else:
            last_handshake = None

        if last_handshake:
            delta = now - last_handshake
            if delta <= timedelta(days=5):
                status_symbol = '✅'
            else:
                status_symbol = '❌'
        else:
            status_symbol = '❌'

        button_text = f"{status_symbol} {username}"
        keyboard.insert(InlineKeyboardButton(button_text, callback_data=f"client_{username}"))

    keyboard.add(InlineKeyboardButton("Домой", callback_data="home"))

    main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))
    if main_chat_id and main_message_id:
        await bot.edit_message_text(
            chat_id=main_chat_id,
            message_id=main_message_id,
            text="Выберите пользователя:",
            reply_markup=keyboard
        )
    else:
        sent_message = await callback_query.message.reply("Выберите пользователя:", reply_markup=keyboard)
        user_main_messages[admin] = (sent_message.chat.id, sent_message.message_id)
        try:
            await bot.pin_chat_message(chat_id=sent_message.chat.id, message_id=sent_message.message_id, disable_notification=True)
        except Exception as e:
            logger.error(f"Не удалось закрепить сообщение: {e}")

    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('client_'))
async def client_selected_callback(callback_query: types.CallbackQuery):
    _, username = callback_query.data.split('client_', 1)
    username = username.strip()

    clients = db.get_client_list()
    client_info = next((c for c in clients if c[0] == username), None)
    if not client_info:
        await callback_query.answer("Ошибка: пользователь не найден.", show_alert=True)
        return

    is_blocked = is_user_blocked(username)
    expiration_time = db.get_user_expiration(username)

    text = f"*Информация о пользователе {username}:*\n"
    if client_info[1]:
        ip_addresses = client_info[1].split(',')
        for ip in ip_addresses:
            ip = ip.strip()
            if not ip:
                continue
            if '/' in ip:
                ip_adr, mask = ip.split('/', 1)
                ip_with_mask = f"{ip_adr}/{mask}"
            else:
                ip_adr = ip
                mask = ''
                ip_with_mask = ip_adr

            if ':' in ip_adr:
                text += f'  IPv6: {ip_with_mask}\n'
            elif '.' in ip_adr:
                text += f'  IPv4: {ip_with_mask}\n'
            else:
                text += f'  IP: {ip_with_mask}\n'
    else:
        text += '  Нет IP-адресов.\n'

    active_clients = db.get_active_list()
    active_info = next((ac for ac in active_clients if ac[0] == username), None)
    if active_info:
        name, last_time, transfer, endpoint = active_info
        text += f'  Последнее подключение: {last_time}\n'
        text += f'  Передача данных: {transfer}\n'
        text += f'  Endpoint: {endpoint}\n'
    else:
        text += '  Нет активных подключений.\n'

    if expiration_time:
        now = datetime.now(pytz.UTC)
        expiration_dt = expiration_time
        if expiration_dt.tzinfo is None:
            expiration_dt = expiration_dt.replace(tzinfo=pytz.UTC)
        remaining = expiration_dt - now
        if remaining.total_seconds() > 0:
            days, seconds = remaining.days, remaining.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            text += f'  Оставшееся время: {days}д {hours}ч {minutes}м\n'

    if is_blocked:
        text += '\n*Статус:* 🔴 Заблокирован'
    else:
        text += '\n*Статус:* 🟢 Активен'

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Удалить", callback_data=f"delete_user_{username}"),
        InlineKeyboardButton("Разблокировать" if is_blocked else "Заблокировать", callback_data=f"{'unblock' if is_blocked else 'block'}_user_{username}"),
    )
    keyboard.add(
        InlineKeyboardButton("IP info", callback_data=f"ip_info_{username}")
    )
    keyboard.add(
        InlineKeyboardButton("Назад", callback_data="list_users"),
        InlineKeyboardButton("Домой", callback_data="home")
    )

    main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))
    if main_chat_id and main_message_id:
        try:
            await bot.edit_message_text(
                chat_id=main_chat_id,
                message_id=main_message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as e:
            if 'Message is not modified' in str(e):
                logger.warning("Попытка изменить сообщение без изменений.")
            else:
                logger.error(f"Ошибка при изменении сообщения: {e}")
    else:
        await callback_query.answer("Ошибка: главное сообщение не найдено.", show_alert=True)
        return

    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('ip_info_'))
async def ip_info_callback(callback_query: types.CallbackQuery):
    _, username = callback_query.data.split('ip_info_', 1)
    username = username.strip()

    active_clients = db.get_active_list()
    active_info = next((ac for ac in active_clients if ac[0] == username), None)
    if active_info:
        endpoint = active_info[3]
        ip_address = endpoint.split(':')[0]
    else:
        await callback_query.answer("Нет информации о подключении пользователя.", show_alert=True)
        return

    url = f"http://ip-api.com/json/{ip_address}?fields=message,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,hosting"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'message' in data:
                        await callback_query.answer(f"Ошибка при получении данных: {data['message']}", show_alert=True)
                        return
                else:
                    await callback_query.answer(f"Ошибка при запросе к API: {resp.status}", show_alert=True)
                    return
    except Exception as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        await callback_query.answer("Ошибка при запросе к API.", show_alert=True)
        return

    info_text = f"*IP информация для {username}:*\n"
    for key, value in data.items():
        info_text += f"{key.capitalize()}: {value}\n"

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Назад", callback_data=f"client_{username}"),
        InlineKeyboardButton("Домой", callback_data="home")
    )

    main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))
    if main_chat_id and main_message_id:
        try:
            await bot.edit_message_text(
                chat_id=main_chat_id,
                message_id=main_message_id,
                text=info_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка при изменении сообщения: {e}")
            await callback_query.answer("Ошибка при обновлении сообщения.", show_alert=True)
            return
    else:
        await callback_query.answer("Ошибка: главное сообщение не найдено.", show_alert=True)
        return

    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('delete_user_'))
async def client_delete_callback(callback_query: types.CallbackQuery):
    username = callback_query.data.split('delete_user_')[1]

    success = db.deactive_user_db(username)
    if success:
        db.remove_user_expiration(username)
        try:
            scheduler.remove_job(job_id=username)
        except:
            pass
        confirmation_text = f"Пользователь **{username}** успешно удален."
    else:
        confirmation_text = f"Не удалось удалить пользователя **{username}**."

    main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))
    if main_chat_id and main_message_id:
        await bot.edit_message_text(
            chat_id=main_chat_id,
            message_id=main_message_id,
            text=confirmation_text,
            parse_mode="Markdown",
            reply_markup=main_menu_markup
        )
    else:
        await callback_query.answer("Ошибка: главное сообщение не найдено.", show_alert=True)
        return

    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('block_user_') or c.data.startswith('unblock_user_'))
async def client_block_callback(callback_query: types.CallbackQuery):
    data = callback_query.data
    if data.startswith('block_user_'):
        action = 'block'
        username = data.split('block_user_')[1]
    elif data.startswith('unblock_user_'):
        action = 'unblock'
        username = data.split('unblock_user_')[1]
    else:
        await callback_query.answer("Неверная команда.", show_alert=True)
        return

    if action == 'block':
        success = await block_user(username)
        if success:
            confirmation_text = f"Пользователь **{username}** заблокирован."
        else:
            confirmation_text = f"Не удалось заблокировать пользователя **{username}**."
    else:
        success = await unblock_user(username)
        if success:
            confirmation_text = f"Пользователь **{username}** разблокирован."
        else:
            confirmation_text = f"Не удалось разблокировать пользователя **{username}**."

    callback_query.data = f'client_{username}'

    await client_selected_callback(callback_query)
    await callback_query.answer(confirmation_text, show_alert=True)

@dp.callback_query_handler(lambda c: c.data == "home")
async def return_home(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != admin:
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    logger.info("Processing 'home' callback")

    main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))
    if main_chat_id and main_message_id:
        user_main_messages.pop('waiting_for_user_name', None)
        user_main_messages.pop('client_name', None)
        user_main_messages.pop('ipv6', None)
        try:
            await bot.edit_message_text(
                chat_id=main_chat_id,
                message_id=main_message_id,
                text="Выберите действие:",
                reply_markup=main_menu_markup
            )
        except Exception as e:
            logger.error(f"Ошибка при изменении сообщения: {e}")
            sent_message = await callback_query.message.reply("Выберите действие:", reply_markup=main_menu_markup)
            user_main_messages[admin] = (sent_message.chat.id, sent_message.message_id)
            try:
                await bot.pin_chat_message(chat_id=sent_message.chat.id, message_id=sent_message.message_id, disable_notification=True)
            except Exception as e:
                logger.error(f"Не удалось закрепить сообщение: {e}")
    else:
        sent_message = await callback_query.message.reply("Выберите действие:", reply_markup=main_menu_markup)
        user_main_messages[admin] = (sent_message.chat.id, sent_message.message_id)
        try:
            await bot.pin_chat_message(chat_id=sent_message.chat.id, message_id=sent_message.message_id, disable_notification=True)
        except Exception as e:
            logger.error(f"Не удалось закрепить сообщение: {e}")

    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "get_config")
async def list_users_for_config(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != admin:
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    clients = db.get_client_list()
    if not clients:
        await callback_query.answer("Список пользователей пуст.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    for client in clients:
        username = client[0]
        keyboard.insert(InlineKeyboardButton(username, callback_data=f"send_config_{username}"))

    keyboard.add(InlineKeyboardButton("Домой", callback_data="home"))

    main_chat_id, main_message_id = user_main_messages.get(admin, (None, None))
    if main_chat_id and main_message_id:
        await bot.edit_message_text(
            chat_id=main_chat_id,
            message_id=main_message_id,
            text="Выберите пользователя для получения конфигурации:",
            reply_markup=keyboard
        )
    else:
        sent_message = await callback_query.message.reply("Выберите пользователя для получения конфигурации:", reply_markup=keyboard)
        user_main_messages[admin] = (sent_message.chat.id, sent_message.message_id)
        try:
            await bot.pin_chat_message(chat_id=sent_message.chat.id, message_id=sent_message.message_id, disable_notification=True)
        except Exception as e:
            logger.error(f"Не удалось закрепить сообщение: {e}")

    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('send_config_'))
async def send_user_config(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != admin:
        await callback_query.answer("У вас нет прав для выполнения этого действия.", show_alert=True)
        return

    _, username = callback_query.data.split('send_config_', 1)
    username = username.strip()

    try:
        with open(f'png/{username}.png', 'rb') as photo, open(f'conf/{username}.conf', 'rb') as config:
            sent_photo = await bot.send_photo(admin, photo)
            sent_doc = await bot.send_document(admin, config)
            asyncio.create_task(delete_message_after_delay(admin, sent_photo.message_id, delay=10))
            asyncio.create_task(delete_message_after_delay(admin, sent_doc.message_id, delay=10))
        confirmation_text = f"Конфигурация для **{username}** отправлена."
    except FileNotFoundError:
        confirmation_text = f"Не удалось найти файлы конфигурации для пользователя **{username}**."
    except Exception as e:
        confirmation_text = f"Произошла ошибка: {str(e)}"

    sent_message = await bot.send_message(
        chat_id=admin,
        text=confirmation_text,
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_message_after_delay(admin, sent_message.message_id, delay=10))

    await callback_query.answer()

@dp.callback_query_handler(lambda c: True)
async def process_unknown_callback(callback_query: types.CallbackQuery):
    await callback_query.answer("Неизвестная команда.", show_alert=True)

async def deactivate_user(client_name: str):
    success = db.deactive_user_db(client_name)
    if success:
        sent_message = await bot.send_message(admin, f"Конфигурация пользователя **{client_name}** истекла и была деактивирована.", parse_mode="Markdown")
        asyncio.create_task(delete_message_after_delay(admin, sent_message.message_id, delay=2))
        db.remove_user_expiration(client_name)
    else:
        sent_message = await bot.send_message(admin, f"Не удалось деактивировать пользователя **{client_name}** по истечении времени.", parse_mode="Markdown")
        asyncio.create_task(delete_message_after_delay(admin, sent_message.message_id, delay=2))

async def on_startup(dp):
    users = db.get_users_with_expiration()
    for user in users:
        client_name, expiration_time = user
        if expiration_time:
            try:
                expiration_datetime = datetime.fromisoformat(expiration_time)
            except ValueError:
                logger.error(f"Неверный формат времени истечения для пользователя {client_name}: {expiration_time}")
                continue

            if expiration_datetime.tzinfo is None:
                expiration_datetime = expiration_datetime.replace(tzinfo=pytz.UTC)
            if expiration_datetime > datetime.now(pytz.UTC):
                scheduler.add_job(
                    deactivate_user,
                    trigger=DateTrigger(run_date=expiration_datetime),
                    args=[client_name],
                    id=client_name
                )
            else:
                await deactivate_user(client_name)

if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup)
