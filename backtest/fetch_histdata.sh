#!/bin/bash
# Download HistData.com free M1 files into data/histdata/ and unzip them.
#   ./fetch_histdata.sh XAUUSD 2025 2026/1 2026/2      ("2025" = whole year, "2026/1" = one month)
set -e
cd "$(dirname "$0")"
mkdir -p data/histdata && cd data/histdata
sym=$1; shift
for p in "$@"; do
  out=${sym}_${p//\//_}.zip
  if [ ! -s "$out" ]; then
    page="https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/${sym,,}/$p"
    form=$(curl -sS -m 60 "$page" | grep -A8 'id="file_down"' \
      | grep -oE 'name="[a-z]+" id="[a-z]+" value="[^"]*"' | sed -E 's/name="([a-z]+)".*value="([^"]*)"/\1=\2/' | paste -sd'&')
    curl -sS -m 120 -e "$page" -d "$form" https://www.histdata.com/get.php -o "$out"
    sleep 3  # be polite
  fi
  unzip -oq "$out" '*.csv'
  echo "$p: $(stat -c%s "$out") bytes"
done
