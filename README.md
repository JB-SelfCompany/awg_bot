# WireGuard/AmneziaWG Telegram Bot

Телеграм-бот на Python для управления [WireGuard](https://www.wireguard.com)/[AmneziaWG](https://github.com/amnezia-vpn/amneziawg-linux-kernel-module). Этот бот позволяет легко управлять клиентами. Подразумевается что у вас уже установлен Python 3.11.x (На 3.12.x возникают ошибки). Используется библиотека aiogram версии 2.25.2.

## Оглавление

- [Возможности](#возможности)
- [Установка](#установка)
- [Запуск](#запуск)
- [Заметки](#заметки)
- [Поддержка](#поддержка)

## Возможности

- Добавление клиентов
- Удаление клиентов
- Блокировка/Разблокировка клиентов
- Создание временных конфигураций (1 час, 1 день, 1 неделя, 1 месяц, неограниченно)
- Получение информации об IP-адресе клиента (берется из Endpoint, используется API с ресурса http://ip-api.com)
- Логирование IP-адресов, откуда было совершено подключение (в разработке)

## Установка

Клонируйте репозиторий:

```bash
git clone https://github.com/JB-SelfCompany/awg_bot.git
cd awg_bot
```

Установите зависимости:

```bash
pip install -r requirements.txt
sudo apt install qrencode -y
```

Убедитесь, что [WireGuard](https://www.wireguard.com)/[AmneziaWG](https://github.com/amnezia-vpn/amneziawg-linux-kernel-module) установлен и настроен на вашем сервере.

### Опционально

Рекомендуется устанавливать библиотеки в виртуальное окружение, затем приступайте к шагу 2 в [Установка](#установка).

Создайте и активируйте виртуальное окружение для Python:

```bash
python3.11 -m venv myenv
source myenv/bin/activate         # Для Linux
python -m venv\Scripts\activate   # Для Windows
```

Создайте бота в телеграмм:

1. Откройте Telegram и найдите бота [BotFather](https://t.me/BotFather).
2. Начните диалог , отправив команду /start.
3. Введите команду /newbot, чтобы создать нового бота.
4. Следуйте инструкциям BotFather, чтобы:
  5. Придумать имя для вашего бота (например, WireGuardManagerBot).
  6. Придумать уникальное имя пользователя для бота (например, WireGuardManagerBot_bot). Оно должно оканчиваться на _bot.
7. После создания бота BotFather отправит вам токен для доступа к API. Его запросит бот во время первоначальной инициализации.

## Запуск

### Опционально

Вы можете воспользоваться скриптом для генерации конфигурации, если это необходимо.

```bash
./genconf.sh
```

Запустите бота:

```bash
cd awg                            # Или cd wg, зависит от того, какой протокол желаете использовать
python3.11 bot_awg.py             # Или bot_wg.py, зависит от того, какой протокол желаете использовать
```

Добавьте бота в Telegram и отправьте команду /start или /help для начала работы.

## Заметки

Вы можете запускать бота как службу, на вашем сервере. Для этого необходимо скопировать файл awg_bot.service в директорию /etc/systemd/system/, и скорректировать параметры внутри с помощью nano:
```bash
nano awg_bot.service
```

Для корректной работы требуется запуск бота от имени пользователя с правами sudo, если [WireGuard](https://www.wireguard.com)/[AmneziaWG](https://github.com/amnezia-vpn/amneziawg-linux-kernel-module) настроен с повышенными привилегиями.
[WireGuard](https://www.wireguard.com)/[AmneziaWG](https://github.com/amnezia-vpn/amneziawg-linux-kernel-module) должен быть настроен и запущен на сервере до использования бота.

## Поддержка

Если у вас возникли вопросы или проблемы с установкой и использованием бота, создайте issue в этом репозитории или обратитесь к администратору.

[Telegram](https://t.me/Mystery_TF)

[Matrix](https://matrix.to/#/@jack_benq:shd.company)
