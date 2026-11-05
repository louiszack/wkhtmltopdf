基于上游 wkhtmltopdf 0.12.7 开发版、带 patched Qt 的 Debian 13（trixie）amd64 安装包，供 Odoo 19 使用。
安装方法和 Odoo 设置见 [ODOO.md](@REPO_URL@/blob/@TAG@/ODOO.md)。

### 下载

```sh
wget @REPO_URL@/releases/download/@TAG@/@DEB@
echo "@SHA256@  @DEB@" | sha256sum -c -
```

### Dockerfile

把 ODOO.md 中 Dockerfile 的两行 `ARG` 换成：

```dockerfile
ARG WKHTMLTOX_URL=@REPO_URL@/releases/download/@TAG@/@DEB@
ARG WKHTMLTOX_SHA256=@SHA256@
```

### 与官方 bookworm 包的区别

- 依赖改为 Debian 13 的包名（`libssl3t64`、`libpng16-16t64` 等），可以直接安装；
- 修复从 PDF 复制/搜索中文时变成部首字符的问题；
- 自带 fontconfig 规则，中文优先使用简体字形的 Noto CJK SC；
- 新增环境变量 `WKHTMLTOPDF_ALLOWED_HOSTS`，限制渲染时可访问的主机（防 SSRF）。

### 已知限制

- 渲染内核是 Qt 4.8.7 / QtWebKit（2015 年），上游早已停止维护，存在不会再修复的安全问题。
  只用它渲染 Odoo 自己生成的报表，并设置 `WKHTMLTOPDF_ALLOWED_HOSTS`。
- Qt 和 WebKit 静态编译在包内；OpenSSL、libpng、libjpeg、FreeType、fontconfig 使用系统库，随 Debian 安全更新。
- 只提供 amd64。

由[这次构建](@RUN_URL@)生成，并已在干净的 Debian 13 上按 Odoo 19 的调用方式测试通过。
