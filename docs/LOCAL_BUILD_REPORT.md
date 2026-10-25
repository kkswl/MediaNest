# 本地构建与提交前验收（2026-10-25）

## 范围与修复

本轮单人串行验证，不访问真实 115/TMDB，不读取现有浏览器配置或 115 Cookie。分支为 main，远程为 kkswl/MediaNest；开始时暂存区为空。现有相关的未提交索引功能、测试、配置及文档经过审查，作为本次本地提交的必要组成；两个既有离线截图不纳入提交、不删除。

本轮新增修复：`app/cli.py` 的 migrate 原来固定打印版本 2，而数据库已经是 v3。现在查询 schema_migrations 的实际最大版本，避免以后再次漂移。`tests/test_cli.py` 在隔离数据库验证 v3 以及模拟后续 v4 的输出，不改动生产数据库。

`README.md` 更新 v3 和受控目录边界，将历史真实烟测与当前离线验证分开。新增 `frontend/playwright.container.config.ts` 和 `frontend/tests/container-smoke.spec.ts`：只接受无凭据的 http://127.0.0.1:<port>/，只使用演示账号，非目标源请求全部拦截，单 worker，关闭可能保存演示会话 Token 的 trace。

没有改技术栈、业务数据库结构或新增业务 API。此前的公开门槛、源海报证据、指定目录范围/预算和租约保护均保留，详细变更清单见 SCOPED_INDEX_DELIVERY.md。

## 检查结果

| 命令 | 结果 |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest -q` | 修复前 93 passed；修复后 94 passed，2 个既有弃用警告 |
| `.venv\Scripts\python.exe -m ruff check --no-cache app tests scripts` | 通过 |
| `npm --prefix frontend run build` | Vite 和 vue-tsc 通过 |
| `npm --prefix frontend audit --omit=dev` | 0 vulnerabilities，仅生产依赖 |
| `docker compose config --quiet` | 原配置和临时验证配置均通过 |
| `git diff --check` | 通过，保留 LF/CRLF 提示，不批量改换行 |
| `interface.spec.ts --workers=1` | Chrome 桌面/移动 18 passed，模拟 API，外部请求拦截 |
| `playwright.container.config.ts --workers=1` | Chrome 桌面/移动 2 passed，连接实际容器 API，外部请求拦截 |

Python 警告来自 Starlette/httpx TestClient 弃用和 raw upload 的 content 参数弃用。Chrome 有 NO_COLOR/FORCE_COLOR 环境警告。镜像构建中的 pip root 警告发生在安装层；最终镜像 USER=yingji，实际运行 UID=10001。没有通过删除测试、放宽断言、跳过失败或 audit fix --force 获得通过。

容器测试覆盖作品墙、版本详情、演示登录/退出、自己的来源、缓存目录树、任务、审核、健康、建议、管理员、审计及导入页面；后台 review 项目逐个从公开详情请求得到 404。浏览目录没有触发索引 POST，浏览器无脚本错误和页面横向溢出。

## Docker 实际构建与问题处理

实际执行了 Compose build，不以配置检查代替镜像构建。

1. 默认构建起初拉取额外 BuildKit 构建器，取消后显式选择已运行的 default 内置构建器，没有修改 Docker 全局设置。
2. 原中文工作区路径遇到 gRPC `x-docker-expose-session-sharedkey` 非 ASCII 错误。改为英文临时构建上下文后越过该错误；原仓库不改名、不搬动。
3. 首次读取 Docker Hub 认证服务连接超时。仅在当前构建进程使用用户已提供的代理，基础镜像、npm/pip 依赖安装及镜像构建成功；没有在仓库或运行容器中固化代理。
4. 将新增测试同步后再次缓存构建成功，60 个源构建输入逐文件 SHA-256 与当前工作区一致。没有复制 .git、.venv、node_modules、dist、data、.env、.npmrc、截图或浏览器产物到上下文。

临时上下文：`C:\Users\Administrator\AppData\Local\Temp\medianest-build-20261025-2b708b07`。

实际命令为在该目录执行 `docker compose --progress plain -p medianest-verify-20261025-2b708b07 build --builder default`，并通过进程变量/构建参数临时提供代理。Node/Python 基础镜像及 npm/pip 来源是软件包仓库，不是 115 资源。

最终本地镜像标识（未推送）：

- `medianest-verify-20261025-2b708b07-web:latest`：`sha256:fc0b0e7391120a674657c31a0ac02ce4b8725f100af26936511cb70978db2adc`
- `medianest-verify-20261025-2b708b07-worker:latest`：`sha256:72df0cddf2c030c69b51bc386b4c1f2682c2f513e85e5136ae008c8720320b8f`

没有启动常驻 worker。仅一次性的 `seed-demo` 执行 105 个串行模拟任务步骤；不是 105 次真实请求。

## 本地容器与访问地址

- 预览地址：<http://127.0.0.1:18080>
- 演示账号：demo / demo-access-2026（仅用于该隔离本机预览，不能用于公网）
- 项目：medianest-verify-20261025-2b708b07
- 容器：medianest-verify-20261025-2b708b07-web-1
- 独立卷：medianest-verify-20261025-2b708b07-demo-data
- 临时 Compose：上述上下文内的 compose.verify.yaml
- API 返回 12 个公开作品、15 个版本、2 个来源，review=0、mock=true、live_enabled=false。
- 容器实际 migrate 输出 v3；健康检查使用本机 /api/stats，实际状态 healthy；ENABLE_LIVE_115 和 ENABLE_TMDB 均为 no。

最初试用 internal 网络时，容器内部健康，但 Docker 没有发布配置的端口，导致两项容器浏览器测试连接拒绝。只重建了本轮的验证容器和网络，保留演示卷，改为独立 bridge 后端口映射及两项浏览器测试通过。最终防护是仅绑定 127.0.0.1、两项真实服务开关关闭、全量 mock 来源及浏览器外部请求拦截；不要宣称最终容器具有额外的出站防火墙隔离。

停止预览（保留演示数据）：

```powershell
docker compose -f C:\Users\Administrator\AppData\Local\Temp\medianest-build-20261025-2b708b07\compose.verify.yaml -p medianest-verify-20261025-2b708b07 down
```

该命令只针对本轮项目，不带 -v，不删除卷、镜像或其他用户服务。临时 Compose 文件若已被系统清理，可用 `docker stop medianest-verify-20261025-2b708b07-web-1` 停止这一明确目标。预览和演示卷暂保留，方便用户查看；重新配置/启动前须确认端口和对象归属。此前试运行的容器及网络已由本轮项目 down 移除并重建，未删除物理数据卷或用户文件。

复跑实际容器浏览器验收：

```powershell
$env:MEDIANEST_CONTAINER_URL = 'http://127.0.0.1:18080/'
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm --prefix frontend run test:e2e -- --config playwright.container.config.ts --workers=1
```

截图及失败上下文只写入忽略的 data/container-smoke-*，不提交。原有 frontend/artifacts/offline-catalog-desktop.png 和 offline-catalog-mobile.png 原样保留。

## Git 与回滚

提交只包含明确审查的相关源码、测试、配置和文档；不使用 git add . / -A，不提交 .env、数据库、密钥、日志、备份、构建产物或截图。提交前审阅暂存 diff、检查敏感值和运行 git diff --cached --check。本地提交哈希以最终 git log 输出为准，不写回本文件造成自引用；没有 push、PR、amend、全局身份修改或跳过钩子。

本轮开始时的脏工作区逐文件备份位于 `G:\拆分115大包\data\development-backups\local-build-20261025-2b708b07`，包含此前的累积功能。若只撤销本轮 CLI/文档/验证测试，应与此副本逐块比较并反向修补，保留前几轮功能和后续用户修改；本轮新测试文件可在确认无其他修改后移到归档目录。不要整仓 reset/restore/clean。

若需要撤销整个本地提交，可在先备份后续改动并确认范围后使用 git revert；这也会撤销提交中收录的此前累积功能，不等于仅撤本轮小修复。数据库 v3 的追加列无需删除，不自动降级或重建数据。容器回滚优先停止本轮预览并保留演示卷，未触及现有生产数据库或用户数据卷。

## 尚未验证

本轮真实 115/TMDB 调用均为 0，没有新增真实分享或凭据。真实子目录/NFO/海报、长期限流、PB/TB 级扫描、PostgreSQL 长期并发、跨主机租约、公网 HTTPS 和正式部署未验证。本地镜像和本机容器通过，不等于这些能力已验证。
