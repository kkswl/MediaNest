# 映集架构

后端使用 FastAPI、SQLAlchemy 和可替换的 SQLite/PostgreSQL 数据库；前端为 Vue 3、Vite、TypeScript 和 Nuxt UI。`MockReader` 只返回虚构目录，`P115Reader` 默认关闭；公开分享可匿名读取分享分页，受限 NFO 仍要求凭据，并且不提供转存、移动、下载或播放接口。

数据库启动先建立 SQLAlchemy 基线，再应用 `schema_migrations` 中记录的显式升级步骤；版本 2 新增来源 `access_status` 和任务 `scan_mode`，兼容早期管理员创建时间和会话撤销字段。可用 `python -m app.cli migrate` 手动触发同一流程，不删除旧数据。

版本 3 为 jobs 追加 `scope_node_id`、`scope_remote_id`、`scope_path`、`scan_requests`、`pages_read`、`nodes_read`，保留旧行和任务 payload 预算。旧预算在 claim 时取较大值继承。升级可重复执行，不删除或降级数据库。

目录扫描任务按分页检查点保存。扫描完成后先分页发现媒体节点，再为每个电影文件或 BDMV 目录创建独立的识别任务；每个任务有租约令牌，提交前会再次核验令牌，过期响应不能覆盖新 worker 的结果。

例外：真实任务默认 `root_preview`，在 claim 事务中预留请求预算（最多两次根目录请求），即使崩溃、暂停、重试也不复位。旧 full 任务也受默认 `LIVE_ROOT_ONLY=yes` 的 worker 边界限制，子目录/识别任务不执行。预览不排子任务，完成状态不代表全量索引。目录树读取不会自动创建新的真实扫描。健康检查在此安全模式只执行一次，不安排 pending 自动复检。

公开列表通过同步 httpx 调用固定 `/share/snap` 端点，无隐式重试、跳转或登录；全局 in-flight 文件锁覆盖完整请求，同时保留请求间隔锁。所有 API/worker 必须共享 STATE_DIR，跨主机分布式互斥不在本次验证范围内。来源访问状态独立于健康，失败回滚后在有效 lease 内保存访问分类；异常消息不包含远端原文。

后台目录树在打开未落库的层级时会创建去重的按目录扫描任务，并返回 `scan_pending`；已存在节点仍由数据库分页返回，避免浏览器展开目录直接阻塞在远端请求上。

上述按需扫描仅保留为模拟来源的旧 API 兼容行为。当前目录树组件只请求缓存数据；真实来源的 GET 即使携带 refresh 也不会创建扫描。搜索不再自动安排真实健康读取，需管理员显式发起复检。

`directory_preview`：管理员对自己来源中已记录的目录调用 `POST /api/admin/sources/{source_id}/directories/{node_id}/scan`，服务端验证节点类型、完整祖先路径和所有权，将范围固定在 Job。worker 在领取及读取前复核范围和唯一扫描任务标识；只读取直接子项，最多两次目录请求，不需要关闭 LIVE_ROOT_ONLY。事务中先用比较交换更新 Job 预算再进行 I/O；暂停、崩溃、重试均不重置。返回 pages_read/nodes_read 是成功提交的页和节点，scan_requests 是已预留的请求（包括失败/崩溃），truncated 表示范围内未读完。

2026-10-26 修复：真实指定目录在成功完成限页读取后，按 scan.payload.seen 中本次实际返回的媒体节点排本地识别任务，双重校验来源/父目录/节点/完成页。真实识别强制 local_only，跳过 NFO 和 TMDB，不递归、不获取内容。已有同作品元数据及人工锁定保留；同源同目录的明确名称/年份或剧集名称/季集可暂时聚合版本，始终 review，禁止跨来源仅凭名称合并。模拟模式继续使用虚构 NFO。

扫描错误也通过 record_health 持久化：根目录失败记录分享健康，指定目录失败只记录该目录健康。uncertain 类错误不增加 missing 次数。API 版本字段分别给出 share_health、node_health、node_kind 和 web_page_status=not_verified，不把目录接口成功当网页验证。mock 版本不公开可点击 share_url；真实链接根据固定分享码和当前访问码构造，原始 URL 不覆盖。

`scripts/verify_scoped.py` 只用于新增人类授权的单来源已有目录回归，通过正常登录、目录索引和复检 API 建任务。唯一同步 worker 限定 job_id/task_id，不领取或恢复无关任务。STATE_DIR/verification 下的运行账本在实际 HTTP 前预留预算（两次指定目录、一次入口健康，不读根目录）；错误后停止，重启不得清空或更换运行 ID 来重获额度。脚本不读取 Cookie/NFO/图片/媒体，不调用 TMDB。账本只含本地 ID、计数和状态，不含分享网址或访问码。

NFO 只在内存解析，数据库只保存结构化字段、来源和人工锁定字段。强 ID 才能跨来源合并；无把握的条目标为待确认。ISO/BDMV 作为作品版本，BDMV/STREAM 子文件不生成条目。公开海报只接受审核过的 HTTPS 域名。

所有公开作品查询统一使用 confirmed + visible + 可用版本门槛；公开统计只计公开作品的版本和来源，兼容的 review 字段恒为 0，后台审核队列仍保留原数据。审核及撤回不删除作品。

`posters.py` 使用 JSON 中的 poster_candidates 保存证据并选择海报：人工锁定 > NFO > 同作品目录 > 外部 > 旧数据未知来源。新增 poster_source/poster_locked/fallback_poster_source，保留 poster/fallback_poster 字段。旧海报不自动认定为人工设置；可验证的旧外部地址可保留为未知来源备用图。同目录多作品禁止任意共享 generic poster.jpg，明确匹配文件名的海报优先。序列化对候选及旧字段重新执行 HTTPS/精确域名白名单检查，不获取图片内容。

健康检查覆盖分享、目录和文件，明确缺失才累计失败；超时、限流、认证和不完整分页保持不确定状态。默认连续 3 次明确缺失才隐藏版本。
