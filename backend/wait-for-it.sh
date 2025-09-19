#!/usr/bin/env bash
# wait-for-it.sh

hostport="$1"
shift

host="$(echo $hostport | cut -d: -f1)"
port="$(echo $hostport | cut -d: -f2)"

while ! nc -z "$host" "$port"; do
  echo "⏳ Aguardando $host:$port..."
  sleep 1
done

echo " $host:$port está pronto!"

exec "$@"
