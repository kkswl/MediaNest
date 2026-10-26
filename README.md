# 映集：115 分享大包影视索引

只读的影视目录索引站。逻辑整理作品、版本和来源，不转存、不移动、不重命名、不下载或播放影视文件。自动回归使用虚构目录；真实烟测需单独授权，不得将模拟测试视为真实 115 可用性证明。

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

Windows 中文路径若遇到 BuildKit 非 ASCII gRPC 错误，可使用英文临时构建上下文并核对源文件哈希，不必改名或移动原仓库。已经实际执行的本地构建、隔离容器验收、访问地址和停止方法见 [docs/LOCAL_BUILD_REPORT.md](docs/LOCAL_BUILD_REPORT.md)。

## 配置与安全边界

配置示例见 `.env.example`。程序从环境变量读取配置；该文件只是示例，直接运行 Python 时请自行设置环境变量，不会自动加载 `.env`。

- `ENABLE_LIVE_115=no`：默认关闭真实读取。切勿为了测试页面就启用真实资源。
- `LIVE_ROOT_ONLY=yes`：默认真实任务仅预览根目录，最多两次目录请求；限制持久化到任务，重启/重试不能重置预算。不产生子目录、识别、NFO 任务。`complete` 只表示限页预览完成，不代表全包已入库。正式递归扫描不在本次验证范围内。
- `ENABLE_TMDB=no`：默认关闭真实 TMDB 请求。仅填写 Token 不会自动授权真实检索。
- `APP_SECRET`：至少 32 字符。未设置时自动创建 `data/app-secret`；其用于凭据加密，与数据库一起备份。更换后已有加密凭据不能正常解密。
- `DATABASE_URL`：默认 SQLite。数据库队列与 API 进程应使用同一数据库和密钥。PostgreSQL 可以通过 SQLAlchemy 连接串配置，但必须单独验证部署和并发行为。
- `SCAN_PAGE_SIZE`、`REQUEST_INTERVAL`：控制分页和限速。不能通过调小间隔规避平台限制。
- `FAILURE_THRESHOLD`：连续明确失败的隐藏阈值，默认 3。网络超时、限流、账号异常不当作资源不存在。
- `TMDB_TOKEN`：只在服务端使用，不放到浏览器代码或公开 API。
- `STATE_DIR=data`：各 worker 与 API 必须共享同一个可加锁目录；持久化密钥及全局 115 请求时钟在此目录中。跨主机部署不能假定本地文件锁提供全局限速。
- `PUBLIC_SOURCE_IMAGE_HOSTS`：默认空；只有人工审核为公开、无凭据访问的源图域名才可配置。不能填内网域名或凭据型图片地址。

公开的 115 分享可以在不配置 Cookie 时读取分享目录分页；需要私有账号权限的操作（包括受限 NFO 读取）仍会分类为认证失败。目录读取始终经过全局限速，且本项目不提供下载、播放、转存或移动接口。

来源 `access_status` 与资源 `health` 独立：`public_listing`（公开目录）、`credential_listing`（账号目录）、`credential_required`（需要账号凭据）、`auth_failed`（账号认证失败）、`rate_limited`（请求受限）、`uncertain`（尚不能确认）。认证、限流、超时和分页不完整均不累计明确失效次数。当前数据库通过新增列迁移到版本 3，保留原有来源和任务；迁移命令显示数据库中实际记录的版本。

管理员也可显式选择自己来源中已缓存的目录，执行 `directory_preview`：仅索引该目录的直接子项，最多两次目录请求、不递归，暂停、重试和重启不恢复请求额度。无需关闭 `LIVE_ROOT_ONLY`。真实目录预览不读取 NFO 或媒体内容。待确认作品只在后台展示，确认且有可用版本后才公开。

指定目录预览现在会为本次实际返回的媒体节点创建本地识别任务，不读取真实 NFO、不请求 TMDB。文件名推断的作品始终进入后台待确认；同来源、同目录的明确片名/年份（或季集）可暂时归组版本，但不跨来源按名字合并。目录包本身不会算成作品。首页数字只计已审核公开作品，不包含分享包、目录节点和待确认作品。

演示版本不提供外部分享链接。真实版本保留原始来源证据，并根据当前访问码生成分享入口地址，不生成未经验证的子目录直达地址。界面区分分享检测、目录/文件存在性和网页打开状态；目录 API 成功不等于网站页面已验证。海报没有可用公开 URL 或浏览器加载失败时，会说明占位原因，不伪造海报。

## 单来源限页验证

先运行全部离线检查。运行 `.venv\Scripts\python.exe scripts/verify_public.py --offline-demo` 可验证单 API、单 worker、根目录预览、节点落库和一次健康检查；它只使用虚构响应。

只有明确授权了唯一来源后，才在启动验证进程的同一 PowerShell 会话中临时提供 `REAL_SHARE_URL`、`REAL_ACCESS_CODE` 及可选 HTTP/HTTPS 代理环境变量，然后执行：

```powershell
.venv\Scripts\python.exe scripts/verify_public.py --confirm-real-read
```

不要把真实值粘贴到项目文件、聊天或命令参数。其他终端中设置的 `$env:` 不会自动传入已经运行的 Codex/其他进程。脚本仅做匿名公开目录验证，不使用 `REAL_COOKIE`，不访问 NFO 或 TMDB；Cookie 不需要提供。它最多请求根目录两次并执行一次健康检查，遇到失败停止扫描回归。限速状态和索引数据库位于唯一临时目录，finally 停止 API 并清理目录。输出仅有脱敏计数和字段名。

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

历史授权记录：此前对单个公开分享做过根目录只读烟测，具体证据及限制见 `docs/VERIFICATION.md`。这些历史结果不代表本轮重新验证，也不代表完整大包可用。2026-10-26 新授权的唯一来源目录回归在首次请求分类为 uncertain 后停止，未新增真实作品；离线回归和候选镜像验收不替代真实服务证明。结果、发布状态及回滚方法见 [本轮交付记录](docs/RELEASE_20261026.md)。真实会话、多页终止、限流、源图、NFO、TMDB 匹配及公网部署仍需单独验证。
