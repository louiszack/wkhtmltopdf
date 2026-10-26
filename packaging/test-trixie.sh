#!/bin/sh
#
# Smoke test a wkhtmltox .deb on a clean Debian 13 "trixie":
# install it, render an Odoo-like report (Chinese text, external CSS served
# over HTTP, header/footer with page numbers, table spanning pages) and check
# the resulting PDF.
#
#   docker run --rm -v "$PWD":/src -w /src debian:trixie \
#       packaging/test-trixie.sh dist/wkhtmltox_*.deb
#
# The rendered PDF/PNG files are written to ./test-output (or $2).

set -eu

DEB=$(realpath "$1")
SRC=$(cd "$(dirname "$0")/.." && pwd)
OUT=$(mkdir -p "${2:-$SRC/test-output}" && cd "${2:-$SRC/test-output}" && pwd)
WWW="$SRC/packaging/testdata"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
    "$DEB" fonts-noto-cjk poppler-utils python3

fail() { echo "FAIL: $*" >&2; exit 1; }

wkhtmltopdf --version
wkhtmltopdf --version | grep -q '(with patched qt)' || fail "wkhtmltopdf not built with patched qt"
wkhtmltoimage --version | grep -q '(with patched qt)' || fail "wkhtmltoimage not built with patched qt"

python3 -m http.server 8069 --bind 127.0.0.1 --directory "$WWW" >/dev/null 2>&1 &
HTTP_PID=$!
trap 'kill $HTTP_PID' EXIT
sleep 1

# same kind of arguments as odoo/addons/base/models/ir_actions_report.py
wkhtmltopdf --disable-local-file-access --quiet \
    --page-size A4 --margin-top 40 --dpi 90 --zoom 1.0666 \
    --header-spacing 35 --margin-left 7 --margin-bottom 32 --margin-right 7 \
    --orientation Portrait \
    --header-html http://127.0.0.1:8069/header.html \
    --footer-html http://127.0.0.1:8069/footer.html \
    http://127.0.0.1:8069/report.html "$OUT/report.pdf"

wkhtmltoimage --quiet --width 800 http://127.0.0.1:8069/report.html "$OUT/report.png"

pdfinfo "$OUT/report.pdf"
pdffonts "$OUT/report.pdf"
pdftotext -layout "$OUT/report.pdf" "$OUT/report.txt"
pdftoppm -png -r 60 -f 1 -l 2 "$OUT/report.pdf" "$OUT/page"

PAGES=$(pdfinfo "$OUT/report.pdf" | sed -n 's/^Pages: *//p')
[ "$PAGES" -ge 2 ] || fail "expected at least 2 pages, got $PAGES"
grep -q '销售订单' "$OUT/report.txt" || fail "Chinese body text missing"
grep -q '样式表已加载' "$OUT/report.txt" || fail "stylesheet not loaded over HTTP"
grep -q '测试公司页眉' "$OUT/report.txt" || fail "header missing"
grep -q "第 *2 *页 */ *共 *$PAGES *页" "$OUT/report.txt" || fail "footer page numbers missing"
pdffonts "$OUT/report.pdf" | grep -q 'CJKsc' || fail "Simplified Chinese CJK font not embedded"
# copied text must use ideographs (用, 页, ...) and not look-alike radicals (⽤, ⻚, ...)
python3 -I -c '
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
radicals = sorted(set(re.findall("[⺀-⿟]", text)))
sys.exit("radicals in PDF text: " + " ".join(radicals) if radicals else 0)
' "$OUT/report.txt" || fail "PDF text contains CJK radicals"

echo "OK: $PAGES pages"
