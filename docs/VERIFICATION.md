# 验证记录

## 2026-10-26：受控识别修复、候选镜像及真实失败边界

本轮 pytest 106 passed（2 个既有警告）、ruff、前端 build、全量与生产 npm audit（均 0 vulnerabilities）、Compose 配置和 diff 空白检查通过。模拟 API 浏览器 20 项、实际隔离容器浏览器 4 项、独立临时模拟数据库本地集成浏览器 2 项通过，均单 worker 并拦截非目标源请求；这些不是实时 115 证明。

唯一授权来源的指定缓存目录仅尝试 1 次真实目录请求，结果 uncertain 后立即停止：成功页/节点 0、健康请求 0，Job 暂停、目录健康事件及预算账本均已持久化，不增加明确失效次数、不隐藏资源。全库作品/版本/节点/待审核没有增加，公开仍 12/15。真实 NFO、海报内容和 TMDB 请求为 0。最终镜像已构建，在独立卷和原 verify.db 卷均 healthy；18080 发布后桌面/移动 preview-smoke 各 1 项通过。完整文件、证据及回滚见 [RELEASE_20261026.md](RELEASE_20261026.md)。以下章节均为历史阶段记录。

## 最新：本地构建与提交前回归

2026-10-25：CLI 迁移版本提示改为读取数据库实际记录，新增回归测试。pytest 94 passed、2 个既有弃用警告，ruff、前端 build、生产依赖 audit（0 vulnerabilities）、Compose 配置和空白检查通过；模拟 API 浏览器 18 passed，实际隔离演示容器浏览器 2 passed，均单 worker，阻断非目标源请求。

本轮 Docker 镜像实际构建成功，并在独立演示卷上 seed-demo、启动 Web、验证 healthy 和 v3 迁移；预览仅绑定 http://127.0.0.1:18080 。没有访问真实 115/TMDB。中文上下文路径、Docker Hub 连接和 internal 网络端口发布问题的诊断、替代流程、镜像标识、停止命令及保留未提交修改的回滚说明见 [LOCAL_BUILD_REPORT.md](LOCAL_BUILD_REPORT.md)。以下“本轮/最新”等表述属于各自历史阶段，不代表本次重复真实验证。

## 最新：公开隔离、海报与受控子目录（离线）

2026-10-25 本轮开发仅使用虚构 demo 与模拟分页，真实 115/TMDB 调用均为 0。pytest 最新 93 passed、2 个既有弃用警告；ruff、前端 build、生产依赖 audit（0 vulnerabilities）、Compose 配置与 diff 空白检查通过。Chrome 单 worker 的 interface.spec.ts 桌面/移动 18 项通过，包含限定目录确认、预算和截断说明、审核海报不误锁定；非本机请求全部拦截。后续若有修改须重跑验证，以最新实际输出为准。

完整修改文件、schema v3、增量 API、证据边界及保留既有脏工作区的回滚方法见 [SCOPED_INDEX_DELIVERY.md](SCOPED_INDEX_DELIVERY.md)。没有进行真实子目录验证、真实海报/NFO/TMDB 验证、Docker 镜像构建或公网部署。以下章节是此前开发阶段的历史记录，不是本轮真实调用证据。

离线回归使用 `demoa`、`demob`、`demotv` 虚构目录，不请求真实 TMDB，不下载视频，不转存或移动文件。

## 上轮授权的真实只读烟测（历史记录）

2026-10-25 对用户授权的一个公开 115 分享执行了小范围串行验证，使用指定 HTTP 代理；没有保存分享链接、访问码或 Cookie。`p115client` 的匿名 `/share/snap` 请求返回成功，分页总数为 1，返回节点字段包含节点 ID、名称、父目录、大小、SHA-1、目录标记和公开图片字段；随后一次健康检查返回 `healthy`，同样只读取根目录。

验证过程没有调用转存、移动、重命名、删除、下载或播放接口。API 与一次性 worker 已启动，导入和 worker tick 已执行；由于 p115client 退出时的非致命清理警告使临时 wrapper 未能输出最终数据库汇总，应用层节点落库数量不作为已验证证据。PB/TB 级递归扫描、真实 NFO 读取、长期限流行为和公网部署仍未验证。

为覆盖该 wrapper 缺口，新增了完全离线的 live-import/worker 集成测试：用模拟的公开 `/share/snap` 响应走真实导入、worker 和节点查询链路，并确认节点落库；这不替代真实 115 的节点落库证据。

已覆盖：批量分享码解析、NFO/GuessIt 字段、XML 外部实体拒绝、演员与合集关系、电影多版本、ISO/BDMV、电视剧季集、分页检查点、任务租约、目录/文件级健康状态、明确缺失阈值、网络错误不隐藏、管理员来源隔离、匿名建议审核和前端桌面/移动布局。

## 本轮开发与离线验收

新增来源访问状态（与 health 独立）、schema v2 保留数据迁移、root_preview 两次目录请求预算、租约成功/失败保护、全请求互斥锁、HTTP 429/401/403/超时/分页不完整分类。CLI `scripts/verify_public.py` 只从进程环境变量取真实参数；匿名公开读取使用同步 httpx 固定端点、无重试/跳转，不导入 SDK 登录流程。

Python 回归：`.venv\\Scripts\\python.exe -m pytest -q` 当前 53 passed、2 warnings。Ruff `--no-cache`、前端 build、生产依赖 `npm audit --omit=dev`、Docker Compose 配置和 `git diff --check` 均通过。两个 Python warning 来自既有测试客户端弃用提示。

使用本机 Chrome 执行 `interface.spec.ts --workers=1`，桌面/移动共 12 项通过，外部请求全部被拦截。覆盖前台“公开目录 / 需要账号凭据”、后台来源访问文本、任务限页提示、登录、任务操作、审核、键盘原生表单和无横向溢出。浏览器自带内部进程不承载 115 请求；本次没有启动并行验证 worker。

`scripts/verify_public.py --offline-demo` 在临时 SQLite 上启动单个 loopback API 和调用方内的单个同步 worker：模拟目录请求 1 次、健康请求 1 次、成功查询并落库 1 节点，health=healthy，临时目录已清理。该条仅为离线证据。

## 本轮真实只读验证结果

用户明确指定了一个不同于上轮的唯一公开电影分享。通过临时 REAL_SHARE_URL / REAL_ACCESS_CODE 和指定 HTTP/HTTPS 代理运行 `scripts/verify_public.py --confirm-real-read`，真实同步请求共 2 次（根目录扫描 1、健康检查 1），扫描返回 1 页、1 节点，数据库 stored_nodes=1，API nodes=1，scan_status=complete（仅根目录预览），access_status=public_listing，health=healthy。没有自动续扫或重复回归该来源。

成功验证节点 ID、名称、父目录 ID、完整相对路径、大小和目录标记的落库/查询字段；分享标题/容量字段存在，但未记录具体值、原始响应或来源地址。真实多页终止和有值的 SHA-1 未验证。所有 115 I/O 在单个同步 worker 中串行完成，没有线程池/多 worker 并发。使用唯一临时数据库，进程结束后已确认 temporary_state_removed=true，API 已停止，Cookie 未使用，未调用 TMDB。没有调用转存、移动、重命名、删除、创建目录、下载、播放或领取远端接口；只有本地临时索引写入。

本次无真实失败结果；auth/auth_failed、timeout、network_error、incomplete、rate_limited、pending/missing 和连续三次明确失败隐藏规则仅由离线注入验证。小范围真实成功不代表 PB/TB 级资源长期稳定性或公网部署已验证。

本轮未进行 Docker 镜像构建、公网部署、PostgreSQL 长期运行或真实多页/NFO/限流验证。上轮 Docker Linux daemon 不可用的失败不能用 compose config 通过来替代。

## 回滚边界

当前修改未提交；开始本轮时已有 7 个文件的改动，不能通过整仓 reset/restore 丢弃它们。先备份当前工作区及数据库/密钥，用 `git diff` 逐块核对并仅撤销本轮新增功能；新增脚本/测试也需核对后再移除。schema v2 是新增列，旧代码可保留列运行；不要自动降级或删除已有索引数据。需要恢复数据库时只使用自己确认的备份。

## 当前变更文件

- 后端：`app/adapters.py`、`app/catalog.py`、`app/cli.py`、`app/config.py`、`app/db.py`、`app/health.py`、`app/main.py`、`app/worker.py`。
- 前端：`frontend/src/api.ts`、`frontend/src/pages/Admin.vue`、`frontend/src/pages/Detail.vue`、`frontend/playwright.config.ts`、`frontend/tests/interface.spec.ts`。
- 验证：`tests/test_adapters.py`、`tests/test_api.py`、新增 `tests/test_public_scope.py`、新增 `scripts/verify_public.py`。
- 配置/文档：`.env.example`、`README.md`、`docs/ARCHITECTURE.md`、`docs/CODING_PROMPT.md`、`docs/VERIFICATION.md`。
- 生成的虚构 UI 截图：`frontend/artifacts/offline-catalog-desktop.png`、`frontend/artifacts/offline-catalog-mobile.png`；不是 115 资源或海报。

以上清单包含开始本轮时已存在的 7 个文件修改；均未自动提交、暂存或推送。本轮技能指导只影响文本状态提示、清晰标签与现有 Nuxt UI 风格，不增加新 UI 框架。

合成性能基准（`.venv\\Scripts\\python.exe scripts/benchmark_index.py --nodes 2000`）在本机临时 SQLite 上创建 2,000 个节点和作品，中文目录搜索命中 1,000 条，查询耗时 56.59 ms，峰值 Python 分配 2.93 MiB。该数据只衡量本地合成查询，不代表真实 115 节点规模或公网性能。

待真实环境验证：115 当前接口字段、真实分页终止、账号认证/限流、源图是否公开、TMDB 鉴权与匹配、PostgreSQL 长时间租约和备份恢复。真实能力未经授权不会启用。
