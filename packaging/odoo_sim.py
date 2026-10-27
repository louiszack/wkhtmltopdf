#!/usr/bin/env python3
#
# Render reports with wkhtmltopdf exactly the way Odoo 19 does
# (odoo/addons/base/models/ir_actions_report.py, web.minimal_layout):
# local temporary files for bodies/header/footer, --disable-local-file-access,
# a session cookie jar, assets loaded over HTTP through <base href=report.url>,
# all headers/footers in one file selected by JavaScript, and RLIMIT_AS
# inherited from the Odoo worker (limit_memory_hard).
#
# Checks the output, measures memory per run and verifies that
# WKHTMLTOPDF_ALLOWED_HOSTS keeps the renderer away from other hosts.
#
#   python3 -I packaging/odoo_sim.py OUTPUT_DIR

import http.server
import json
import os
import re
import resource
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

REPORT_URL = 'http://127.0.0.1:8069'  # ir.config_parameter report.url
OTHER_HOST = '127.0.0.2'              # stands in for any other server on the LAN
SESSION = 'odoo-sim-session'
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'testdata')

LIMITS = [('1GiB', 1024 << 20), ('2.5GiB', 2560 << 20)]  # limit_memory_hard
ALLOWED_HOSTS = '127.0.0.1,localhost'

# paperformat_euro (default A4) as passed by _build_wkhtmltopdf_args
ODOO_ARGS = [
    '--disable-local-file-access', '--quiet',
    '--page-size', 'A4', '--margin-top', '52.0', '--dpi', '90', '--zoom', str(96.0 / 90),
    '--header-spacing', '52', '--margin-left', '0.0', '--margin-bottom', '32.0',
    '--margin-right', '0.0', '--orientation', 'Portrait', '--javascript-delay', '1000',
]

# from web.minimal_layout
SUBST_JS = """
function subst() {
    var vars = {};
    var x = document.location.search.substring(1).split('&');
    for (var i in x) {
        var z = x[i].split('=', 2);
        vars[z[0]] = unescape(z[1]);
    }
    var x = ['sitepage', 'sitepages', 'section', 'subsection', 'subsubsection'];
    var z = {'sitepage': 'page', 'sitepages': 'topage'};
    for (var i in x) {
        var y = document.getElementsByClassName(z[x[i]] || x[i])
        for (var j=0; j<y.length; ++j)
            y[j].textContent = vars[x[i]];
    }

    var index = vars['webpage'].split('.', 4)[3];
    var header = document.getElementById('minimal_layout_report_headers');
    if(header){
        var companyHeader = header.children[index];
        header.textContent = '';
        header.appendChild(companyHeader);
    }
    var footer = document.getElementById('minimal_layout_report_footers');
    if(footer){
        var companyFooter = footer.children[index];
        footer.textContent = '';
        footer.appendChild(companyFooter);
    }
}
"""

failures = []


def check(ok, message):
    print(('ok   ' if ok else 'FAIL ') + message)
    if not ok:
        failures.append(message)


def noise_png(width, height):
    """An incompressible RGB image, like a product photo."""
    rows = b''.join(b'\x00' + os.urandom(width * 3) for _ in range(height))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 1))
            + chunk(b'IEND', b''))


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(('0.0.0.0', 8069), Handler)
        self.requests = []
        self.images = {}
        self.lock = threading.Lock()

    def requests_to(self, ip):
        return [r for r in self.requests if r['ip'] == ip]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC, **kwargs)

    def log_message(self, *args):
        pass

    def do_GET(self):
        with self.server.lock:
            self.server.requests.append({
                'ip': self.connection.getsockname()[0],  # address the renderer connected to
                'path': self.path,
                'cookie': self.headers.get('Cookie', ''),
            })
        if self.path == '/redirect-other-host':
            self.send_response(302)
            self.send_header('Location', f'http://{OTHER_HOST}:8069/probe/redirected')
            self.end_headers()
        elif self.path.startswith('/probe/') or self.path.startswith('/img/'):
            if self.path not in self.server.images:
                size = 400 if self.path.startswith('/img/') else 1
                self.server.images[self.path] = noise_png(size, size)
            data = self.server.images[self.path]
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()


def layout(body, subst):
    script = f'<script>{SUBST_JS}</script>' if subst else ''
    onload = ' onload="subst()"' if subst else ''
    return f"""<!DOCTYPE html>
<html style="height: 0;">
<head>
<base href="{REPORT_URL}"/>
<link type="text/css" rel="stylesheet" href="/style.css"/>
<meta charset="utf-8"/>
{script}
</head>
<body class="o_body_pdf o_css_margins container overflow-hidden"{onload}>
{body}
</body>
</html>"""


def document(n, rows, images=0, extra=''):
    lines = '\n'.join(
        f'<tr><td>{i}</td><td>办公用品 {i} 号（A4 打印纸）</td>'
        f'<td class="num">{i % 7 + 1}</td><td class="num">¥ {i * 12.5:,.2f}</td></tr>'
        for i in range(1, rows + 1))
    pictures = ''.join(f'<img src="/img/{k}.png" style="width: 120px;"/>' for k in range(images))
    return f"""<div class="article"><div class="page">
<h1>销售订单 S{n:05d}</h1>
<p class="css-check"></p>
<p>客户：上海示例贸易有限公司　地址：上海市浦东新区世纪大道 100 号</p>
<table>
<thead><tr><th>序号</th><th>产品描述</th><th>数量</th><th>金额</th></tr></thead>
<tbody>
{lines}
</tbody>
</table>
<div>{pictures}</div>
{extra}
<p>合计金额（大写）：壹万贰仟元整</p>
</div></div>"""


def headers_footers(count):
    header = ''.join(f'<div class="header">测试公司页眉 文档{n}</div>' for n in range(1, count + 1))
    footer = ''.join(
        f'<div class="footer" style="text-align: center;">文档{n} 第 <span class="page"></span> 页 / '
        f'共 <span class="topage"></span> 页</div>' for n in range(1, count + 1))
    return (layout(f'<div id="minimal_layout_report_headers">{header}</div>', True),
            layout(f'<div id="minimal_layout_report_footers">{footer}</div>', True))


def run_wkhtmltopdf(bodies, header, footer, output, limit=None, env=None):
    """Same steps as IrActionsReport._run_wkhtmltopdf, plus memory sampling."""
    files = []

    def temp(prefix, suffix, content):
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix)
        with os.fdopen(fd, 'wb') as f:
            f.write(content.encode())
        files.append(path)
        return path

    try:
        args = list(ODOO_ARGS)
        args += ['--cookie-jar', temp('report.cookie_jar.tmp.', '.txt',
                                      f'session_id={SESSION}; HttpOnly; domain=127.0.0.1; path=/;')]
        args += ['--header-html', temp('report.header.tmp.', '.html', header)]
        args += ['--footer-html', temp('report.footer.tmp.', '.html', footer)]
        args += [temp(f'report.body.tmp.{i}.', '.html', body) for i, body in enumerate(bodies)]
        args += [output]

        def limit_memory():
            # odoo.service.server.set_limit_memory_hard, inherited by the subprocess
            if limit:
                soft, hard = resource.getrlimit(resource.RLIMIT_AS)
                resource.setrlimit(resource.RLIMIT_AS, (limit, hard))

        stderr = tempfile.TemporaryFile()
        started = time.monotonic()
        process = subprocess.Popen(['wkhtmltopdf', *args], stdout=subprocess.DEVNULL, stderr=stderr,
                                   preexec_fn=limit_memory, env={**os.environ, **(env or {})})
        vm_peak = rss_peak = 0
        while process.poll() is None:
            try:
                with open(f'/proc/{process.pid}/status') as f:
                    status = f.read()
                vm_peak = max(vm_peak, int(re.search(r'VmPeak:\s+(\d+)', status).group(1)))
                rss_peak = max(rss_peak, int(re.search(r'VmHWM:\s+(\d+)', status).group(1)))
            except (OSError, AttributeError):
                pass
            if time.monotonic() - started > 900:
                process.kill()
            time.sleep(0.02)
        stderr.seek(0)
        return {
            'returncode': process.returncode,
            'seconds': round(time.monotonic() - started, 1),
            'vm_peak_mib': vm_peak // 1024,
            'rss_peak_mib': rss_peak // 1024,
            'stderr': stderr.read().decode(errors='replace')[-1000:],
        }
    finally:
        for path in files:
            os.unlink(path)


def pdf_text(path):
    return subprocess.run(['pdftotext', '-layout', path, '-'], capture_output=True, text=True).stdout


def pdf_pages(path):
    info = subprocess.run(['pdfinfo', path], capture_output=True, text=True).stdout
    match = re.search(r'^Pages:\s+(\d+)', info, re.M)
    return int(match.group(1)) if match else 0


def main(out):
    os.makedirs(out, exist_ok=True)
    server = Server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results = []

    def record(scenario, limit_name, result, pages):
        result = {'scenario': scenario, 'limit': limit_name, 'pages': pages, **result}
        results.append(result)
        print(f"  {scenario} @ {limit_name}: exit {result['returncode']}, {pages} pages, "
              f"{result['seconds']}s, VmPeak {result['vm_peak_mib']} MiB, RSS {result['rss_peak_mib']} MiB")
        return result

    # --- several documents in one call (printing a batch of quotations) ---
    print('batch: 3 documents, Odoo multi-document header/footer')
    docs = 3
    bodies = [layout(document(n, 60), False) for n in range(1, docs + 1)]
    header, footer = headers_footers(docs)
    for name, limit in LIMITS:
        pdf = os.path.join(out, f'batch-{name}.pdf')
        result = record('batch', name, run_wkhtmltopdf(bodies, header, footer, pdf, limit), pdf_pages(pdf))
    # functional checks on the last (recommended) limit, the others are only measured
    check(result['returncode'] == 0, f"batch: wkhtmltopdf exit code 0 (got {result['returncode']})")
    text = pdf_text(pdf)
    with open(os.path.join(out, 'batch.txt'), 'w') as f:
        f.write(text)
    for n in range(1, docs + 1):
        check(f'销售订单 S{n:05d}' in text, f'batch: document {n} body present')
        check(f'测试公司页眉 文档{n}' in text, f'batch: document {n} has its own header')
        check(re.search(fr'文档{n} *第 *1 *页 */ *共 *\d+ *页', text) is not None,
              f'batch: document {n} footer numbers its own pages')
    check(text.count('样式表已加载') == docs, 'batch: stylesheet loaded over HTTP via <base href>')
    css = [r for r in server.requests if r['path'] == '/style.css']
    check(bool(css) and all(f'session_id={SESSION}' in r['cookie'] for r in css),
          'batch: session cookie from --cookie-jar sent with asset requests')
    radicals = sorted(set(re.findall('[⺀-⿟]', text)))
    check(not radicals, f"batch: no CJK radicals in copied text {' '.join(radicals)}")
    fonts = subprocess.run(['pdffonts', pdf], capture_output=True, text=True).stdout
    check('CJKsc' in fonts, 'batch: Simplified Chinese Noto CJK font embedded')
    subprocess.run(['pdftoppm', '-png', '-r', '60', '-f', '1', '-l', '2', pdf, os.path.join(out, 'batch-page')])

    # --- one large document with product images ---
    print('large: 3000 rows, 30 images')
    bodies = [layout(document(1, 3000, images=30), False)]
    header, footer = headers_footers(1)
    for name, limit in LIMITS:
        pdf = os.path.join(out, f'large-{name}.pdf')
        result = record('large', name, run_wkhtmltopdf(bodies, header, footer, pdf, limit), pdf_pages(pdf))
    check(result['returncode'] == 0, f"large: wkhtmltopdf exit code 0 (got {result['returncode']})")
    check('办公用品 3000 号' in pdf_text(pdf), 'large: last table row present')
    images = subprocess.run(['pdfimages', '-list', pdf], capture_output=True, text=True).stdout
    check(len(images.splitlines()) - 2 >= 30, 'large: product images embedded')

    # --- SSRF: requests to other hosts, with and without the allowlist ---
    print(f'ssrf: report content pointing at {OTHER_HOST}')
    probes = f"""
<img src="http://{OTHER_HOST}:8069/probe/img"/>
<img src="/redirect-other-host"/>
<img src="http://2130706434:8069/probe/decimal-ip"/>
<div style="background-image: url(http://{OTHER_HOST}:8069/probe/css-background);">x</div>
<link rel="stylesheet" href="http://{OTHER_HOST}:8069/probe/stylesheet"/>
<iframe src="http://{OTHER_HOST}:8069/probe/iframe"></iframe>
<script>
try {{
    var xhr = new XMLHttpRequest();
    xhr.open('GET', 'http://{OTHER_HOST}:8069/probe/xhr', false);
    xhr.send();
}} catch (e) {{}}
</script>"""
    bodies = [layout(document(1, 5, extra=probes), False)]
    header, footer = headers_footers(1)

    del server.requests[:]
    pdf = os.path.join(out, 'ssrf-open.pdf')
    run_wkhtmltopdf(bodies, header, footer, pdf)
    reached = sorted(r['path'] for r in server.requests_to(OTHER_HOST))
    print(f'  without allowlist {OTHER_HOST} received: {reached}')
    check('/probe/img' in reached, f'ssrf: control run reaches {OTHER_HOST} (test is effective)')

    del server.requests[:]
    pdf = os.path.join(out, 'ssrf-allowlist.pdf')
    result = run_wkhtmltopdf(bodies, header, footer, pdf, env={'WKHTMLTOPDF_ALLOWED_HOSTS': ALLOWED_HOSTS})
    reached = sorted(r['path'] for r in server.requests_to(OTHER_HOST))
    print(f'  with WKHTMLTOPDF_ALLOWED_HOSTS={ALLOWED_HOSTS} {OTHER_HOST} received: {reached}')
    check(result['returncode'] in (0, 1), f"ssrf: report still rendered (exit {result['returncode']})")
    check(not reached, f'ssrf: allowlist blocks every request to {OTHER_HOST}')
    check('样式表已加载' in pdf_text(pdf), 'ssrf: allowed host still serves the stylesheet')
    check(any(r['path'] == '/redirect-other-host' for r in server.requests),
          'ssrf: redirect from an allowed host was requested, its target was blocked')

    # --- wkhtmltoimage as called by IrActionsReport._run_wkhtmltoimage ---
    fd, html = tempfile.mkstemp(suffix='.html', prefix='report_image_html_input.tmp.')
    with os.fdopen(fd, 'wb') as f:
        f.write(layout(document(1, 10), False).encode())
    image = os.path.join(out, 'image.jpg')
    process = subprocess.run(['wkhtmltoimage', '--disable-local-file-access', '--disable-javascript', '--quiet',
                              '--width', '800', '--height', '600', '--format', 'jpg', html, image])
    os.unlink(html)
    check(process.returncode == 0 and os.path.getsize(image) > 0, 'wkhtmltoimage: Odoo arguments produce an image')

    server.shutdown()

    with open(os.path.join(out, 'memory.json'), 'w') as f:
        json.dump(results, f, indent=2)
    table = ['| scenario | limit_memory_hard | exit | pages | seconds | VmPeak MiB | RSS peak MiB |',
             '|---|---|---|---|---|---|---|']
    table += [f"| {r['scenario']} | {r['limit']} | {r['returncode']} | {r['pages']} | {r['seconds']} "
              f"| {r['vm_peak_mib']} | {r['rss_peak_mib']} |" for r in results]
    print('\n'.join(table))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write('### wkhtmltopdf memory (Odoo-style calls)\n\n' + '\n'.join(table) + '\n')

    if failures:
        sys.exit(f'{len(failures)} check(s) failed')
    print('all checks passed')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'test-output')
