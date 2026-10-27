wkhtmltopdf and wkhtmltoimage
-----------------------------

wkhtmltopdf and wkhtmltoimage are command line tools to render HTML into PDF
and various image formats using the QT Webkit rendering engine. These run
entirely "headless" and do not require a display or display service.

See https://wkhtmltopdf.org for updated documentation.

## Building
wkhtmltopdf has its own dedicated repository for building and packaging.

See https://github.com/wkhtmltopdf/packaging

## Debian 13 (trixie) / Odoo 19

This fork builds a patched-Qt package for Debian 13, see [ODOO.md](ODOO.md).
