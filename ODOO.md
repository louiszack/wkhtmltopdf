# 在 Odoo 19（Debian 13 trixie）中使用 wkhtmltopdf

本仓库为 Debian 13 构建带 patched Qt 的 `wkhtmltox` 安装包（amd64），
在 [Releases](https://github.com/louiszack/wkhtmltopdf/releases) 下载
`wkhtmltox_*.trixie_amd64.deb`。

与官方 bookworm 包相比：

- 依赖改为 Debian 13 的包名（`libssl3t64`、`libpng16-16t64` 等），可以直接安装；
- 修复从 PDF 复制/搜索中文时变成部首字符的问题（如「用」变成「⽤」）；
- 自带 fontconfig 规则，中文优先使用简体字形的 Noto CJK SC（西文仍用 DejaVu）。

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

### workers

不要设置 `workers = 1`：唯一的 worker 在等待 wkhtmltopdf 时无法响应它回调取 CSS 的请求，
会卡死。用 `workers = 0`（多线程模式）或 `workers >= 2`。

## 3. 自行构建

```sh
git submodule update --init
docker run --rm -v "$PWD":/src -w /src debian:trixie packaging/build-trixie.sh
docker run --rm -v "$PWD":/src -w /src debian:trixie packaging/test-trixie.sh dist/wkhtmltox_*.deb
```

构建脚本会先应用 `packaging/patches/qt/` 下的 Qt 补丁。
推送 tag 时 GitHub Actions 会自动构建、测试并发布到 Releases。
