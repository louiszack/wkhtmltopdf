#!/bin/sh
#
# Test a wkhtmltox .deb on a clean Debian 13 "trixie": install it and render
# reports the way Odoo 19 does (see odoo_sim.py), checking the output, memory
# use under Odoo's limit_memory_hard and the WKHTMLTOPDF_ALLOWED_HOSTS
# allowlist.
#
#   docker run --rm -v "$PWD":/src -w /src debian:trixie \
#       packaging/test-trixie.sh dist/wkhtmltox_*.deb
#
# The rendered PDFs, page images and memory.json are written to
# ./test-output (or $2).

set -eu

DEB=$(realpath "$1")
SRC=$(cd "$(dirname "$0")/.." && pwd)
OUT=$(mkdir -p "${2:-$SRC/test-output}" && cd "${2:-$SRC/test-output}" && pwd)

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
    "$DEB" fonts-noto-cjk poppler-utils python3

wkhtmltopdf --version
wkhtmltopdf --version | grep -q '(with patched qt)' || { echo "FAIL: wkhtmltopdf not built with patched qt" >&2; exit 1; }
wkhtmltoimage --version | grep -q '(with patched qt)' || { echo "FAIL: wkhtmltoimage not built with patched qt" >&2; exit 1; }

python3 -I "$SRC/packaging/odoo_sim.py" "$OUT"
