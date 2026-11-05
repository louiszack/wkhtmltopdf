wkhtmltopdf for Debian 13 (trixie) / Odoo 19
--------------------------------------------

This fork of the archived [wkhtmltopdf/wkhtmltopdf](https://github.com/wkhtmltopdf/wkhtmltopdf)
builds the `wkhtmltox` package with patched Qt for Debian 13 (trixie), amd64,
and tests it the way Odoo 19 calls it.

- Download: [Releases](https://github.com/louiszack/wkhtmltopdf/releases)
- Installation, Odoo settings and known limitations: [ODOO.md](ODOO.md) (in Chinese)
- Build: `packaging/build-trixie.sh` in a `debian:trixie` container, see [ODOO.md](ODOO.md)

Changes from the official bookworm package:

- depends on the Debian 13 package names (`libssl3t64`, `libpng16-16t64`, ...);
- Chinese text copied from PDFs no longer turns into CJK radicals;
- Simplified Chinese glyphs (Noto CJK SC) are preferred;
- `WKHTMLTOPDF_ALLOWED_HOSTS` restricts which hosts a render may reach.

The rendering engine is Qt 4.8.7 / QtWebKit, which is no longer maintained:
use it only for trusted HTML such as Odoo's own reports.

wkhtmltopdf and wkhtmltoimage
-----------------------------

wkhtmltopdf and wkhtmltoimage are command line tools to render HTML into PDF
and various image formats using the QT Webkit rendering engine. These run
entirely "headless" and do not require a display or display service.

See https://wkhtmltopdf.org for updated documentation.

## Building
Upstream builds and packages in https://github.com/wkhtmltopdf/packaging
(archived, no Debian 13 target). This fork builds with `packaging/build-trixie.sh`.
