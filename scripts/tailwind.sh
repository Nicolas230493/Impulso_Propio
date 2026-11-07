#!/usr/bin/env bash
# Compila static/css/app.css con el CLI standalone de Tailwind (sin Node).
# Uso: scripts/tailwind.sh          -> compila minificado
#      scripts/tailwind.sh --watch  -> recompila al guardar
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=v3.4.17
BIN=bin/tailwindcss
if [[ ! -x $BIN ]]; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) ARCH=linux-x64 ;;
    Linux-aarch64) ARCH=linux-arm64 ;;
    Darwin-arm64) ARCH=macos-arm64 ;;
    Darwin-x86_64) ARCH=macos-x64 ;;
    *) echo "Plataforma no soportada"; exit 1 ;;
  esac
  mkdir -p bin
  curl -sfL -o "$BIN" "https://github.com/tailwindlabs/tailwindcss/releases/download/$VERSION/tailwindcss-$ARCH"
  chmod +x "$BIN"
fi
exec "$BIN" -i assets/tailwind.css -o static/css/app.css --minify "$@"
