# WireGuard / AmneziaWG Telegram Bot

Телеграм-бот на Python для управления [WireGuard](https://www.wireguard.com) / [AmneziaWG](https://github.com/amnezia-vpn/amneziawg-linux-kernel-module). Этот бот позволяет легко управлять клиентами. Подразумевается, что у вас уже установлен Python 3.11.x (на 3.12.x возникают ошибки). Используется библиотека `aiogram` версии 2.25.2.

## Оглавление

- [Возможности](#возможности)
- [Установка](#установка)
- [Запуск](#запуск)
- [Заметки](#заметки)
- [Поддержка](#поддержка)

## Возможности

- Добавление клиентов
- Удаление клиентов
- Блокировка/разблокировка клиентов
- Создание временных конфигураций (1 час, 1 день, 1 неделя, 1 месяц, неограниченно)
- Получение информации об IP-адресе клиента (берется из Endpoint, используется API ресурса [ip-api.com](http://ip-api.com))
- Логирование IP-адресов, откуда было совершено подключение (в разработке)

## Установка

1. Установите [WireGuard](https://www.wireguard.com) или [AmneziaWG](https://github.com/amnezia-vpn/amneziawg-linux-kernel-module) (без данного шага бот РАБОТАТЬ НЕ БУДЕТ).

2. Клонируйте репозиторий:

    ```bash
    git clone https://github.com/JB-SelfCompany/awg_bot.git
    cd awg_bot
    ```

    #### Опционально (рекомендуется устанавливать библиотеки в виртуальное окружение)

    Создайте и активируйте виртуальное окружение для Python:

    ```bash
    python3.11 -m venv myenv
    source myenv/bin/activate          # Для Linux
    python -m myenv\Scripts\activate   # Для Windows
    ```

3. Установите зависимости:

    ```bash
    pip install -r requirements.txt
    sudo apt update && sudo apt install qrencode -y
    ```

4. Создайте бота в Telegram:

    - Откройте Telegram и найдите бота [BotFather](https://t.me/BotFather).
    - Начните диалог, отправив команду `/start`.
    - Введите команду `/newbot`, чтобы создать нового бота.
    - Следуйте инструкциям BotFather, чтобы:
        - Придумать имя для вашего бота (например, `WireGuardManagerBot`).
        - Придумать уникальное имя пользователя для бота (например, `WireGuardManagerBot_bot`). Оно должно оканчиваться на `_bot`.
    - После создания бота BotFather отправит вам токен для доступа к API. Его запросит бот во время первоначальной инициализации.

## Запуск

#### Опционально

Вы можете воспользоваться скриптом для генерации конфигурации, если настраиваете [WireGuard](https://www.wireguard.com) или [AmneziaWG](https://github.com/amnezia-vpn/amneziawg-linux-kernel-module) в первый раз.

    ./genconf.sh

1. Запустите бота:

    ```bash
    cd awg                             # Или cd wg, зависит от того, какой протокол желаете использовать
    python3.11 bot_awg.py              # Или bot_wg.py, зависит от того, какой протокол желаете использовать
    ```
    
2. Добавьте бота в Telegram и отправьте команду `/start` или `/help` для начала работы.

## Заметки

Вы можете запускать бота как службу на вашем сервере. Для этого:

1. Скопируйте файл `awg_bot.service` в директорию `/etc/systemd/system/`:

    ```bash
    sudo cp awg_bot.service /etc/systemd/system/
    ```

2. Отредактируйте параметры внутри файла с помощью `nano` (или любого удобного текстового редактора):

    ```bash
    sudo nano /etc/systemd/system/awg_bot.service
    ```
    
3. Перезагрузите системный демон и запустите службу:

    ```bash
    sudo systemctl daemon-reload
    sudo systemctl start awg_bot.service
    sudo systemctl enable awg_bot.service
    ```
    
**Важно:** Для корректной работы требуется запуск бота от имени пользователя с правами `sudo`, если [WireGuard](https://www.wireguard.com) / [AmneziaWG](https://github.com/amnezia-vpn/amneziawg-linux-kernel-module) настроен с повышенными привилегиями. [WireGuard](https://www.wireguard.com) / [AmneziaWG](https://github.com/amnezia-vpn/amneziawg-linux-kernel-module) должен быть настроен и запущен на сервере до использования бота.

## Поддержка

Если у вас возникли вопросы или проблемы с установкой и использованием бота, создайте [issue](https://github.com/JB-SelfCompany/awg_bot/issues) в этом репозитории или обратитесь к администратору.

- [Telegram](https://t.me/Mystery_TF)
- [Matrix](https://matrix.to/#/@jack_benq:shd.company)
