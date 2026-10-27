# 在 Odoo 19（Debian 13 trixie）中使用 wkhtmltopdf

本仓库为 Debian 13 构建带 patched Qt 的 `wkhtmltox` 安装包（amd64），
在 [Releases](https://github.com/louiszack/wkhtmltopdf/releases) 下载
`wkhtmltox_*.trixie_amd64.deb`。

与官方 bookworm 包相比：

- 依赖改为 Debian 13 的包名（`libssl3t64`、`libpng16-16t64` 等），可以直接安装；
- 修复从 PDF 复制/搜索中文时变成部首字符的问题（如「用」变成「⽤」）；
- 自带 fontconfig 规则，中文优先使用简体字形的 Noto CJK SC（西文仍用 DejaVu）；
- 新增环境变量 `WKHTMLTOPDF_ALLOWED_HOSTS`，限制渲染时只能访问指定主机（防 SSRF）。

每次构建都会在干净的 Debian 13 上按 Odoo 19 的方式调用测试（[packaging/odoo_sim.py](packaging/odoo_sim.py)）：
本地临时文件、`--disable-local-file-access`、cookie-jar、多文档页眉页脚、`limit_memory_hard` 内存上限。

## 1. 安装

### 方式 A：在运行中的容器里安装（测试用）

容器 **重启** 后仍然有效，但 **重建**（修改/升级 TrueNAS 应用、`docker compose up` 重新创建）后会丢失。

```sh
wget https://github.com/louiszack/wkhtmltopdf/releases/download/<tag>/<deb 文件名>
docker cp <deb 文件名> <odoo 容器>:/tmp/
docker exec -u root <odoo 容器> sh -c 'apt-get update && apt-get install -y /tmp/<deb 文件名> fonts-noto-cjk'
docker exec <odoo 容器> wkhtmltopdf --version    # 必须包含 (with patched qt)
docker restart <odoo 容器>
```

### 方式 B：写进 Dockerfile（长期使用）

```dockerfile
USER root

ARG WKHTMLTOX_URL=https://github.com/louiszack/wkhtmltopdf/releases/download/<tag>/<deb 文件名>
ARG WKHTMLTOX_SHA256=<sha256>
ADD ${WKHTMLTOX_URL} /tmp/wkhtmltox.deb
RUN echo "${WKHTMLTOX_SHA256}  /tmp/wkhtmltox.deb" | sha256sum -c - \
    && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb fonts-noto-cjk \
    && rm -rf /tmp/wkhtmltox.deb /var/lib/apt/lists/*

USER odoo
```

镜像中如已装有 Debian 自带的（未打补丁的）`wkhtmltopdf`，apt 会自动替换。

## 2. Odoo 设置

### PDF 没有样式 / 版式错乱

wkhtmltopdf 在 **Odoo 容器内部** 通过 HTTP 访问 Odoo 获取 CSS。
如果 `web.base.url` 是外部域名（反向代理、HTTPS、容器内无法解析），PDF 会只有文字没有样式。

在 **设置 → 技术 → 系统参数** 新增：

| 键 | 值 |
|---|---|
| `report.url` | `http://127.0.0.1:8069` |

（端口按 Odoo 在容器内实际监听的端口填写。）

设置后 wkhtmltopdf 不再经过公网域名访问 Odoo。wkhtmltopdf 会忽略 SSL 证书错误，
而 Odoo 会交给它一个临时会话 cookie，所以 `web.base.url` 是 https 时更应该这样设置。

注意：`dbfilter` 若按域名匹配（含 `%h`/`%d`），通过 127.0.0.1 访问会选不到数据库；
`dbfilter` 写死库名（如 `^Odoo$`）则没有问题。

### workers

不要设置 `workers = 1`：唯一的 worker 在等待 wkhtmltopdf 时无法响应它回调取 CSS 的请求，
会卡死。用 `workers = 0`（多线程模式）或 `workers >= 2`。

## 3. 安全与资源

### 限制 wkhtmltopdf 可访问的主机（防 SSRF）

报表里的图片、样式、iframe、脚本请求会由 wkhtmltopdf 真正发出。若报表内容中出现
指向内网的地址（如 `<img src="http://192.168.1.1/...">`），容器就会替它访问内网
（TrueNAS 管理页、路由器等）。`--disable-local-file-access` 只拦本地文件，不拦 http/https。

在 TrueNAS 的 YAML 中给 Odoo 容器加环境变量（Odoo 启动的 wkhtmltopdf 会继承）：

```yaml
services:
  odoo:
    environment:
      WKHTMLTOPDF_ALLOWED_HOSTS: "127.0.0.1,localhost"
```

- 只允许列出的主机（精确匹配，不看端口），跳转、iframe、XHR、CSS 中的地址同样受限；
- 不设置该变量时行为与原版一致；设置为空字符串则禁止所有网络访问；
- 前提是已按上文把 `report.url` 设为 `http://127.0.0.1:8069`；
- 若报表中需要显示某个外部网站的图片，把那个主机名加进列表。排查时可在容器里手动运行
  `wkhtmltopdf` 且不加 `--quiet`，被拦截的请求会输出 `Blocked access to host ...`。

### 内存（实测）

Odoo 在多进程模式（`workers > 0`）下用 `limit_memory_hard` 设置 RLIMIT_AS，
wkhtmltopdf 子进程继承同样的上限。CI 中按 Odoo 方式实测（x86-64，4 核）：

| 报表 | 页数 | 耗时 | 虚拟内存峰值 | 实际内存峰值 |
|---|---|---|---|---|
| 批量 3 份报价单 | 9 | 2.5 秒 | 314 MiB | 55 MiB |
| 3000 行 + 30 张图片 | 101 | 3.8 秒 | 402 MiB | 145 MiB |
| 10000 行 + 200 张图片 | 339 | 12 秒 | 672 MiB | 418 MiB |

`limit_memory_hard = 1073741824`（1GiB）下以上全部成功。若遇到
`Wkhtmltopdf failed (error code: -11)`，说明报表超过上限，调高 `limit_memory_hard`。

建议在 YAML 中给容器设总内存上限，避免异常时影响 NAS 上的其他服务：

```yaml
services:
  odoo:
    deploy:
      resources:
        limits:
          memory: 6G
```

### 门户网站的 PDF 下载

门户用户（以及持有分享链接的人）可以反复下载 PDF，每次都会启动一个 wkhtmltopdf。
`workers = 2` 时最多同时渲染 2 份，内存可控，但大量请求会让网站变慢。
可在反向代理上对 `/report/` 和带 `report_type=pdf` 的地址做限流。
已过账发票的 PDF 会被 Odoo 存为附件，重复下载不会重新渲染。

## 4. 自行构建

```sh
git submodule update --init
docker run --rm -v "$PWD":/src -w /src debian:trixie packaging/build-trixie.sh
docker run --rm -v "$PWD":/src -w /src debian:trixie packaging/test-trixie.sh dist/wkhtmltox_*.deb
```

构建脚本会先应用 `packaging/patches/qt/` 下的 Qt 补丁。
推送 tag 时 GitHub Actions 会自动构建、测试并发布到 Releases。
