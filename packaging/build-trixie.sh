#!/bin/sh
#
# Build a wkhtmltox .deb (with patched Qt) for Debian 13 "trixie".
#
# Run inside a debian:trixie container, from a checkout that has the qt
# submodule initialized:
#
#   git submodule update --init
#   docker run --rm -v "$PWD":/src -w /src debian:trixie packaging/build-trixie.sh
#
# The resulting package is written to ./dist (or the directory given as $1).
#
# Environment:
#   ITERATION   debian revision of the package (default: 1)
#   JOBS        parallel make jobs (default: nproc)
#   BUILD_DIR   build directory (default: ./build-trixie)
#   SKIP_DEPS   set to 1 to skip installing build dependencies via apt

set -eu

SRC=$(cd "$(dirname "$0")/.." && pwd)
OUT=$(mkdir -p "${1:-$SRC/dist}" && cd "${1:-$SRC/dist}" && pwd)
BUILD=${BUILD_DIR:-$SRC/build-trixie}
ITERATION=${ITERATION:-1}
JOBS=${JOBS:-$(nproc)}

if [ ! -x "$SRC/qt/configure" ]; then
    echo "Qt sources not found, run: git submodule update --init" >&2
    exit 1
fi

if [ "${SKIP_DEPS:-0}" != 1 ]; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends \
        build-essential \
        ccache \
        git \
        libfontconfig-dev \
        libfreetype-dev \
        libjpeg62-turbo-dev \
        libpng-dev \
        libssl-dev \
        libx11-dev \
        libxext-dev \
        libxrender-dev \
        perl \
        python-is-python3 \
        python3 \
        zlib1g-dev
fi

# GCC 14 turns several old C idioms into hard errors, -fpermissive makes them
# warnings again. GCC 13+ no longer pulls in <stdint.h> transitively.
export CFLAGS="-w -fpermissive"
export CXXFLAGS="-w -fpermissive -include stdint.h"
export PATH="/usr/lib/ccache:$PATH"
export CCACHE_DIR="${CCACHE_DIR:-$SRC/.ccache}"

# same as the "common" + "docker" qt-config of wkhtmltopdf/packaging
QT_CONFIG="
    -opensource -confirm-license -fast -release -static
    -graphicssystem raster -webkit -exceptions -xmlpatterns
    -system-zlib -system-libpng -system-libjpeg
    -no-libmng -no-libtiff -no-accessibility -no-stl -no-qt3support
    -no-phonon -no-phonon-backend -no-opengl -no-declarative
    -no-script -no-scripttools
    -no-sql-db2 -no-sql-ibase -no-sql-mysql -no-sql-oci -no-sql-odbc
    -no-sql-psql -no-sql-sqlite -no-sql-sqlite2 -no-sql-tds
    -no-mmx -no-3dnow -no-sse -no-sse2 -no-multimedia
    -nomake demos -nomake docs -nomake examples -nomake tools
    -nomake tests -nomake translations
    -silent -xrender -largefile -iconv -openssl-linked
    -no-javascript-jit -no-rpath -no-dbus -no-nis -no-cups -no-pch
    -no-gtkstyle -no-nas-sound -no-sm -no-xshape -no-xinerama
    -no-xcursor -no-xfixes -no-xrandr -no-mitshm -no-xinput -no-xkb
    -no-glib -no-gstreamer -no-icu -no-openvg -no-xsync
    -no-audio-backend -no-sse3 -no-ssse3 -no-sse4.1 -no-sse4.2
    -no-avx -no-neon
"

for p in "$SRC"/packaging/patches/qt/*.patch; do
    if patch -d "$SRC/qt" -p1 -R -s -f --dry-run < "$p" > /dev/null 2>&1; then
        echo "already applied: $p"
    else
        patch -d "$SRC/qt" -p1 -N < "$p"
    fi
done

mkdir -p "$BUILD/qt" "$BUILD/app"

cd "$BUILD/qt"
if [ ! -f .configured ]; then
    # shellcheck disable=SC2086
    "$SRC/qt/configure" $QT_CONFIG --prefix="$BUILD/qt"
    touch .configured
fi
if [ ! -f mkspecs/modules/qt_webkit_version.pri ]; then
    echo "Qt was configured without WebKit" >&2
    exit 1
fi
make -j"$JOBS"

# version: 0.12.7-dev => 0.12.7~dev.<commit date>.g<commit>
VERSION_TEXT=$(cat "$SRC/VERSION")
case "$VERSION_TEXT" in
*-*)
    GIT="git -C $SRC -c safe.directory=*"
    if COMMIT=$($GIT rev-parse --short=8 HEAD 2>/dev/null); then
        DATE=$($GIT log -1 --format=%cd --date=format:%Y%m%d)
        UPSTREAM="${VERSION_TEXT%%-*}~${VERSION_TEXT#*-}.$DATE.g$COMMIT"
    else
        UPSTREAM="${VERSION_TEXT%%-*}~${VERSION_TEXT#*-}.$(date +%Y%m%d)"
    fi
    ;;
*)
    UPSTREAM=$VERSION_TEXT
    ;;
esac
DEB_VERSION="$UPSTREAM-$ITERATION.trixie"
ARCH=$(dpkg --print-architecture)

PKG="$BUILD/pkg"
rm -rf "$PKG" "$BUILD/app"/*
mkdir -p "$PKG/DEBIAN" "$PKG/usr/local"

cd "$BUILD/app"
"$BUILD/qt/bin/qmake" "$SRC/wkhtmltopdf.pro" CONFIG+=silent
make -j"$JOBS"
# installed binaries and library are already stripped by qmake
make install INSTALL_ROOT="$PKG/usr/local"

FONTCONF=etc/fonts/conf.d/64-wkhtmltox-noto-cjk-sc.conf
install -D -m 644 "$SRC/packaging/fontconfig/${FONTCONF##*/}" "$PKG/$FONTCONF"
echo "/$FONTCONF" > "$PKG/DEBIAN/conffiles"

# resolve shared library dependencies with the trixie package names
# (libssl3t64, libpng16-16t64, ...) instead of hardcoding them
mkdir -p "$BUILD/shlibs/debian"
echo "Source: wkhtmltox" > "$BUILD/shlibs/debian/control"
(cd "$BUILD/shlibs" && dpkg-shlibdeps -O --ignore-missing-info \
    -l"$PKG/usr/local/lib" \
    "$PKG"/usr/local/bin/wkhtmltopdf \
    "$PKG"/usr/local/bin/wkhtmltoimage \
    "$PKG"/usr/local/lib/libwkhtmltox.so.*.*.*) > "$BUILD/shlibs/substvars"
SHLIBS=$(sed -n 's/^shlibs:Depends=//p' "$BUILD/shlibs/substvars")
if [ -z "$SHLIBS" ]; then
    echo "dpkg-shlibdeps found no dependencies" >&2
    exit 1
fi

cat > "$PKG/DEBIAN/control" <<EOF
Package: wkhtmltox
Version: 1:$DEB_VERSION
Architecture: $ARCH
Maintainer: louiszack <louiszack@users.noreply.github.com>
Installed-Size: $(du -sk "$PKG/usr" | cut -f1)
Depends: $SHLIBS, ca-certificates, fontconfig, xfonts-75dpi, xfonts-base
Provides: wkhtmltopdf
Conflicts: wkhtmltopdf
Replaces: wkhtmltopdf
Section: utils
Priority: optional
Homepage: https://github.com/louiszack/wkhtmltopdf
Description: convert HTML to PDF and various image formats using QtWebkit
 wkhtmltopdf and wkhtmltoimage built with the patched Qt for Debian 13
 (trixie), suitable for Odoo reports.
EOF
echo "libwkhtmltox 0 wkhtmltox (>= 0.12.0)" > "$PKG/DEBIAN/shlibs"
echo "activate-noawait ldconfig" > "$PKG/DEBIAN/triggers"

DEB="$OUT/wkhtmltox_${DEB_VERSION}_$ARCH.deb"
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$DEB"
dpkg-deb --info "$DEB"
echo "built $DEB"
