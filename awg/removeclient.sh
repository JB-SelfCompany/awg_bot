#!/bin/bash

set -e

# Проверка аргументов
if [ -z "$1" ]; then
    echo "Error: CLIENT_NAME argument is not provided"
    exit 1
fi

if [ -z "$2" ]; then
    echo "Error: WG_CONFIG_FILE argument is not provided"
    exit 1
fi

CLIENT_NAME="$1"
WG_CONFIG_FILE="$2"

# Удаление клиента из конфигурационного файла WireGuard
sed -i "/^# BEGIN_PEER $CLIENT_NAME$/, /^# END_PEER $CLIENT_NAME$/d" "$WG_CONFIG_FILE"

# Перезагрузка конфигурации WireGuard
awg syncconf $(basename "$WG_CONFIG_FILE" .conf) <(awg-quick strip $(basename "$WG_CONFIG_FILE" .conf))

echo "Client $CLIENT_NAME successfully removed from AmneziaWG"
