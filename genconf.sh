#!/bin/bash

choose_config_type() {
    echo "Выберите тип конфигурации:" >&2
    echo "1) AmneziaWG" >&2
    echo "2) Wireguard" >&2
    echo -n "Введите номер: " >&2
    read config_type
    if [[ -z "$config_type" ]]; then
        config_type=1
    fi
    while [[ ! "$config_type" =~ ^[1-2]$ ]]; do
        echo "Неверный выбор. Пожалуйста, введите 1 или 2." >&2
        echo -n "Введите номер: " >&2
        read config_type
        if [[ -z "$config_type" ]]; then
            config_type=1
        fi
    done
    CONFIG_TYPE="$config_type"
}

check_installed() {
    if [[ "$CONFIG_TYPE" -eq 1 ]]; then
        if ! command -v awg >/dev/null 2>&1; then
            echo "AmneziaWG не установлен в системе. Обратитесь к ресурсу https://github.com/amnezia-vpn/amneziawg-linux-kernel-module" >&2
            exit 1
        fi
    else
        if ! command -v wg >/dev/null 2>&1; then
            echo "WireGuard не установлен в системе. Обратитесь к ресурсу https://www.wireguard.com/install" >&2
            exit 1
        fi
    fi
}

choose_port() {
    while true; do
        echo -n "Какой порт использовать? " >&2
        read port
        if [[ "$port" =~ ^[0-9]+$ ]]; then
            PORT="$port"
            break
        else
            echo "Порт должен быть числом." >&2
        fi
    done
}

choose_ipv6() {
    ip6_address=""
    ipv6_list=($(ip -6 addr | grep 'inet6 [23]' | cut -d '/' -f1 | grep -oE '([0-9a-fA-F]{0,4}:){1,7}[0-9a-fA-F]{0,4}'))
    if [[ ${#ipv6_list[@]} -gt 0 ]]; then
        echo "Доступны подсети IPv6:" >&2
        for i in "${!ipv6_list[@]}"; do
            index=$((i + 1))
            echo "$index) ${ipv6_list[$i]}" >&2
        done
        last_option=$(( ${#ipv6_list[@]} +1 ))
        echo "$last_option) Не использовать" >&2
        echo -n "Введите номер: " >&2
        read ip6_number
        until [[ "$ip6_number" =~ ^[0-9]+$ && "$ip6_number" -ge 1 && "$ip6_number" -le "$last_option" ]]; do
            echo "$ip6_number: неверный выбор." >&2
            echo -n "Введите номер: " >&2
            read ip6_number
        done
        if [[ "$ip6_number" -le ${#ipv6_list[@]} ]]; then
            selected_ipv6=${ipv6_list[$((ip6_number -1))]}
            IFS=':' read -r -a segments <<< "$selected_ipv6"
            if [[ "${segments[0]}" =~ ^200 ]]; then
                segments[0]=300
                base_ipv6="${segments[0]}:${segments[1]}:${segments[2]}:${segments[3]}"
                ip6_address="${base_ipv6}::1/64"
            else
                echo "Первый сегмент IPv6 адреса не начинается с 200. IPv6 адрес не будет добавлен." >&2
            fi
        fi
    fi
    echo "$ip6_address"
}

generate_private_key() {
    local type=$1
    if [[ "$type" -eq 1 ]]; then
        private_key=$(awg genkey)
    else
        private_key=$(wg genkey)
    fi
    echo "$private_key"
}

get_next_config_number() {
    local dir=$1
    local prefix=$2
    local current_number=0
    while [[ -f "$dir/${prefix}${current_number}.conf" ]]; do
        current_number=$((current_number +1))
    done
    echo "$current_number"
}

choose_config_type
check_installed
choose_port
ip6_address=$(choose_ipv6)
private_key=$(generate_private_key "$CONFIG_TYPE")

if [[ "$CONFIG_TYPE" -eq 1 ]]; then
    config_dir="/etc/amnezia/amneziawg"
    config_prefix="awg"
else
    config_dir="/etc/wireguard"
    config_prefix="wg"
fi

mkdir -p "$config_dir"
config_number=$(get_next_config_number "$config_dir" "$config_prefix")
config_file="${config_dir}/${config_prefix}${config_number}.conf"
interface_name="${config_prefix}${config_number}"

if [[ "$CONFIG_TYPE" -eq 1 ]]; then
    Jc=4
    Jmin=15
    Jmax=1268
    S1=131
    S2=45
    H1=1004746675
    H2=1157755290
    H3=1273046607
    H4=2137162994
fi

used_ipv4=()
shopt -s nullglob
for file in "$config_dir"/*.conf; do
    addresses=$(grep 'Address =' "$file" | awk -F'=' '{print $2}' | tr ',' '\n' | sed 's/ //g')
    for addr in $addresses; do
        if [[ "$addr" =~ ^10\.0\.0\.([0-9]{1,3})/32$ ]]; then
            used_ipv4+=("${BASH_REMATCH[1]}")
        fi
    done
done
shopt -u nullglob

octet=1
while [[ " ${used_ipv4[@]} " =~ " $octet " ]]; do
    ((octet++))
done
if [ "$octet" -gt 254 ]; then
    echo "Error: WireGuard internal subnet 10.0.0.0/24 is full" >&2
    exit 1
fi
address="10.0.0.$octet/32"
if [[ -n "$ip6_address" ]]; then
    address="${address}, ${ip6_address}"
fi

if [[ "$CONFIG_TYPE" -eq 1 ]]; then
    cat <<EOF > "$config_file"
[Interface]
Address = $address

Jc = $Jc
Jmin = $Jmin
Jmax = $Jmax
S1 = $S1
S2 = $S2
H1 = $H1
H2 = $H2
H3 = $H3
H4 = $H4

ListenPort = $PORT
PrivateKey = $private_key

PostUp = iptables -t nat -A POSTROUTING -o \$(ip route | awk '/default/ {print \$5; exit}') -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -o \$(ip route | awk '/default/ {print \$5; exit}') -j MASQUERADE
EOF
    echo "Конфигурация AmneziaWG создана: $config_file" >&2
else
    cat <<EOF > "$config_file"
[Interface]
Address = $address

ListenPort = $PORT
PrivateKey = $private_key

PostUp = iptables -t nat -A POSTROUTING -o \$(ip route | awk '/default/ {print \$5; exit}') -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -o \$(ip route | awk '/default/ {print \$5; exit}') -j MASQUERADE
EOF
    echo "Конфигурация Wireguard создана: $config_file" >&2
fi
chmod 600 "$config_file"
echo "Генерация конфигурации завершена успешно." >&2

if [[ "$CONFIG_TYPE" -eq 1 ]]; then
    awg-quick up "$interface_name"
    systemctl enable awg-quick@"$interface_name"
else
    wg-quick up "$interface_name"
    systemctl enable wg-quick@"$interface_name"
fi
