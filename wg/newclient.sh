#!/bin/bash

set -e

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

if [ "$4" == "ipv6" ]; then
    IPV6="yes"
else
    IPV6="no"
fi

if [[ ! "$CLIENT_NAME" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Error: Invalid CLIENT_NAME. Only letters, numbers, underscores, and hyphens are allowed."
    exit 1
fi

octet=2
while grep -E "AllowedIPs\s*=\s*10\.0\.0\.$octet/32" "$WG_CONFIG_FILE" > /dev/null; do
    (( octet++ ))
done

if [ "$octet" -gt 254 ]; then
    echo "Error: WireGuard internal subnet 10.0.0.0/24 is full"
    exit 1
fi

pwd=$(pwd)

mkdir -p "$pwd/conf" "$pwd/png"

key=$(wg genkey)
psk=$(wg genpsk)

if [ "$IPV6" == "yes" ]; then
    ipv6_subnet=$(awk '
        /^\[Interface\]/ {flag=1; next}
        /^\[/ {flag=0}
        flag && /^Address\s*=/ {
            n=split($0, a, ",")
            for(i=1;i<=n;i++) {
                gsub(/^[ ]+|[ ]+$/, "", a[i])
                if(a[i] ~ /:/) {
                    split(a[i], b, "/")
                    ipv6_addr=b[1]
                    if (match(ipv6_addr, /^(.*)::[0-9a-fA-F]+$/, arr)) {
                        print arr[1]"::/64"
                        exit
                    } else {
                        match(ipv6_addr, /^(.*):[^:]+$/, arr)
                        if (arr[1] != "") {
                            print arr[1]":/64"
                            exit
                        }
                    }
                }
            }
        }
    ' "$WG_CONFIG_FILE")

    if [ -z "$ipv6_subnet" ]; then
        echo "Error: IPv6 subnet not found in WireGuard configuration."
        exit 1
    fi

    prefix=$(echo "$ipv6_subnet" | sed 's/\(.*\)::.*$/\1::/')

    ipv6_subnet_escaped=${ipv6_subnet//:/\\:}

    existing_ipv6=$(grep -E "^AllowedIPs\s*=\s*10\.0\.0\.\d+/32,\s*${ipv6_subnet_escaped}[0-9a-fA-F]+/128" "$WG_CONFIG_FILE" | awk -F',' '{print $2}' | awk '{print $1}' | sed "s|${prefix}||" | sed 's|/128||')

    max_host=1
    for ip_suffix in $existing_ipv6; do
        if [[ "$ip_suffix" =~ ^[0-9a-fA-F]+$ ]]; then
            host_num=$((16#$ip_suffix))
            if [ "$host_num" -gt "$max_host" ]; then
                max_host=$host_num
            fi
        fi
    done
    next_host_num=$((max_host +1))
    client_ipv6="${prefix}${next_host_num}/128"
    ALLOWED_IPS="10.0.0.$octet/32, $client_ipv6"
else
    ALLOWED_IPS="10.0.0.$octet/32"
fi

server_private_key=$(awk '/^PrivateKey\s*=/ {print $3}' "$WG_CONFIG_FILE")
if [ -z "$server_private_key" ]; then
    echo "Error: Server PrivateKey not found in WireGuard configuration."
    exit 1
fi
server_public_key=$(echo "$server_private_key" | wg pubkey)

cat << EOF >> "$WG_CONFIG_FILE"
# BEGIN_PEER $CLIENT_NAME
[Peer]
PublicKey = $(echo "$key" | wg pubkey)
PresharedKey = $psk
AllowedIPs = $ALLOWED_IPS
# END_PEER $CLIENT_NAME
EOF

if [ "$IPV6" == "yes" ]; then
    listen_port=$(awk '/ListenPort\s*=/ {print $3}' "$WG_CONFIG_FILE")
    cat << EOF > "$pwd/conf/$CLIENT_NAME.conf"
[Interface]
Address = 10.0.0.$octet/32, ${client_ipv6}
DNS = 8.8.8.8
PrivateKey = $key

[Peer]
PublicKey = $server_public_key
PresharedKey = $psk
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = $ENDPOINT:$listen_port
PersistentKeepalive = 25
EOF
else
    listen_port=$(awk '/ListenPort\s*=/ {print $3}' "$WG_CONFIG_FILE")
    cat << EOF > "$pwd/conf/$CLIENT_NAME.conf"
[Interface]
Address = 10.0.0.$octet/32
DNS = 8.8.8.8
PrivateKey = $key

[Peer]
PublicKey = $server_public_key
PresharedKey = $psk
AllowedIPs = 0.0.0.0/0
Endpoint = $ENDPOINT:$listen_port
PersistentKeepalive = 25
EOF
fi

qrencode -l L < "$pwd/conf/$CLIENT_NAME.conf" -o "$pwd/png/$CLIENT_NAME.png"

wg addconf "$(basename "$WG_CONFIG_FILE" .conf)" <(sed -n "/^# BEGIN_PEER $CLIENT_NAME$/, /^# END_PEER $CLIENT_NAME$/p" "$WG_CONFIG_FILE")

echo "Client $CLIENT_NAME successfully added to WireGuard"
