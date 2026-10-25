# 映集：115 分享大包影视索引

只读的影视目录索引站。逻辑整理作品、版本和来源，不转存、不移动、不重命名、不下载或播放影视文件。开发和测试数据全部为虚构目录；不得将模拟测试视为真实 115 可用性证明。

## 本地运行

要求 Python 3.12+、Node.js 22+。在项目目录打开 PowerShell：

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --timeout 120 --retries 3 -r requirements.lock
.venv\Scripts\python.exe -m pip install --no-deps -e .
npm --prefix frontend ci
npm --prefix frontend run build
.venv\Scripts\python.exe -m app.cli seed-demo
.venv\Scripts\python.exe -m app.cli serve --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000 。另开终端运行持久化队列 worker：

```powershell
.venv\Scripts\python.exe -m app.cli worker
```

`seed-demo` 是显式的本地演示命令，创建 `demo / demo-access-2026`、`curator / curator-access-2026` 两个演示管理员并整理模拟来源。它不访问 115。不要在真实或公网环境保留这些已公开的演示密码。

生产用途必须自行创建管理员，不执行演示命令：

```powershell
.venv\Scripts\python.exe -m app.cli init-admin --username your-admin --password "replace-with-a-long-random-password"
```

已有数据库升级或首次部署时可显式运行迁移命令：

```powershell
.venv\Scripts\python.exe -m app.cli migrate
```

后台管理员登录与将来可能增加的访客登录领取是不同功能。本期没有访客注册、领取、转存、播放入口。

## 本地 Docker

以下配置仅绑定本机 `127.0.0.1`，不会主动公开到局域网或公网：

```powershell
docker compose build
docker compose run --rm web python -m app.cli seed-demo
docker compose up -d
```

数据库和加密密钥保存在 `yingji-data` 卷中；不要执行 `docker compose down -v`，否则会删除本地演示数据库和密钥。普通停止使用 `docker compose down`，数据卷保留。Docker 构建需要访问软件包仓库，不访问 115 分享。

## 配置与安全边界

配置示例见 `.env.example`。程序从环境变量读取配置；该文件只是示例，直接运行 Python 时请自行设置环境变量，不会自动加载 `.env`。

- `ENABLE_LIVE_115=no`：默认关闭真实读取。切勿为了测试页面就启用真实资源。
- `ENABLE_TMDB=no`：默认关闭真实 TMDB 请求。仅填写 Token 不会自动授权真实检索。
- `APP_SECRET`：至少 32 字符。未设置时自动创建 `data/app-secret`；其用于凭据加密，与数据库一起备份。更换后已有加密凭据不能正常解密。
- `DATABASE_URL`：默认 SQLite。数据库队列与 API 进程应使用同一数据库和密钥。PostgreSQL 可以通过 SQLAlchemy 连接串配置，但必须单独验证部署和并发行为。
- `SCAN_PAGE_SIZE`、`REQUEST_INTERVAL`：控制分页和限速。不能通过调小间隔规避平台限制。
- `FAILURE_THRESHOLD`：连续明确失败的隐藏阈值，默认 3。网络超时、限流、账号异常不当作资源不存在。
- `TMDB_TOKEN`：只在服务端使用，不放到浏览器代码或公开 API。
- `STATE_DIR=data`：各 worker 与 API 必须共享同一个可加锁目录；持久化密钥及全局 115 请求时钟在此目录中。跨主机部署不能假定本地文件锁提供全局限速。
- `PUBLIC_SOURCE_IMAGE_HOSTS`：默认空；只有人工审核为公开、无凭据访问的源图域名才可配置。不能填内网域名或凭据型图片地址。

服务器只保存结构化元数据，不保存源包海报、背景图、原始 NFO 或影视内容。小 NFO 在内存解析；浏览器直接加载经过 URL 校验的公开海报，失败时回退。需要后台认证或携带签名参数的源海报不公开。访客建议的网址不允许直接变成任意服务端抓取请求。

模拟分享代码 `demoa`、`demob`、`demotv` 由本地适配器处理，URL 文本仅为测试输入。不得将虚构 URL 作为真实资源宣传。

## 验证

```powershell
.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run build
.venv\Scripts\python.exe scripts/collect_licenses.py
.venv\Scripts\python.exe scripts/benchmark_index.py --nodes 2000
```

具体覆盖范围、结果和未验证能力见 [docs/VERIFICATION.md](docs/VERIFICATION.md)。设计和实现说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。开源来源及许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 已知边界

PB 容量不代表文件数量；扫描耗时取决于目录节点数量、接口限流和失败重试。任务应渐进入库，不能承诺瞬间处理整个大包。

浏览器缓存受浏览器和远端 HTTP 缓存策略控制；网站不能保证每位访客永不重新请求。未验证稳定的 115 子目录直达，前台只应提供原分享和完整路径。文件名中的音轨或字幕信息是推断，不是实际媒体探测。

本项目未获准扫描此前真实分享，也未部署公网。真实 115 会话、分页、错误码、限流和源图访问、TMDB 鉴权与检索均需另行授权后用小范围测试资源验证。
