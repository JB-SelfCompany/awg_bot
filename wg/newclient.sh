#!/bin/bash

set -e

# Проверка аргументов
if [ -z "$1" ]; then
    echo "Error: CLIENT_NAME argument is not provided"
    exit 1
fi

if [ -z "$2" ]; then
    echo "Error: ENDPOINT argument is not provided"
    exit 1
fi

if [ -z "$3" ]; then
    echo "Error: WG_CONFIG_FILE argument is not provided"
    exit 1
fi

CLIENT_NAME="$1"
ENDPOINT="$2"
WG_CONFIG_FILE="$3"

# Проверка наличия опционального аргумента 'ygg'
if [ "$4" == "ygg" ]; then
    YGG="yes"
else
    YGG="no"
fi

# Проверка имени клиента на допустимые символы
if [[ ! "$CLIENT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Error: Invalid CLIENT_NAME. Only letters, numbers, underscores, and hyphens are allowed."
    exit 1
fi

# Get the next available internal IPv4 address for the client
octet=2
while grep AllowedIPs "$WG_CONFIG_FILE" | grep -q "10\.10\.0\.$octet/32"; do
    (( octet++ ))
done

if [ "$octet" -gt 254 ]; then
    echo "Error: WireGuard internal subnet is full"
    exit 1
fi

# Get the current directory
pwd=$(pwd)

# Check if the conf and png directories exist, create them if not
mkdir -p "$pwd/conf" "$pwd/png"

# Generate the keys and PSK
key=$(wg genkey)
psk=$(wg genpsk)

# Проверка наличия 'ygg' и формирование AllowedIPs
if [ "$YGG" == "yes" ]; then
    YGG_SUBNET=$(yggdrasilctl getSelf | awk '/IPv6 subnet/{print $3}' | cut -d '/' -f 1)
    ALLOWED_IPS="10.10.0.$octet/32, ${YGG_SUBNET}$octet/128"
else
    ALLOWED_IPS="10.10.0.$octet/32"
fi

# Добавление клиента
cat << EOF >> "$WG_CONFIG_FILE"
# BEGIN_PEER $CLIENT_NAME
[Peer]
PublicKey = $(echo $key | wg pubkey)
PresharedKey = $psk
AllowedIPs = $ALLOWED_IPS
# END_PEER $CLIENT_NAME
EOF

# Создание конфигурационного файла клиента
if [ "$YGG" == "yes" ]; then
    cat << EOF > "$pwd/conf/$CLIENT_NAME.conf"
[Interface]
Address = 10.10.0.$octet/24, ${YGG_SUBNET}$octet/64
DNS = 8.8.8.8
PrivateKey = $key

[Peer]
PublicKey = $(awk '/PrivateKey/{print $3}' "$WG_CONFIG_FILE" | wg pubkey)
PresharedKey = $psk
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = $ENDPOINT:$(awk '/ListenPort/{print $3}' "$WG_CONFIG_FILE")
PersistentKeepalive = 25
EOF
else
    cat << EOF > "$pwd/conf/$CLIENT_NAME.conf"
[Interface]
Address = 10.10.0.$octet/24
DNS = 8.8.8.8
PrivateKey = $key

[Peer]
PublicKey = $(awk '/PrivateKey/{print $3}' "$WG_CONFIG_FILE" | wg pubkey)
PresharedKey = $psk
AllowedIPs = 0.0.0.0/0
Endpoint = $ENDPOINT:$(awk '/ListenPort/{print $3}' "$WG_CONFIG_FILE")
PersistentKeepalive = 25
EOF
fi

# Генерация QR-кода для конфигурации клиента
qrencode -l L < "$pwd/conf/$CLIENT_NAME.conf" -o "$pwd/png/$CLIENT_NAME.png"

# Перезагрузка конфигурации WireGuard
wg addconf $(basename "$WG_CONFIG_FILE" .conf) <(sed -n "/^# BEGIN_PEER $CLIENT_NAME$/, /^# END_PEER $CLIENT_NAME$/p" "$WG_CONFIG_FILE")

echo "Client $CLIENT_NAME successfully added to WireGuard"
