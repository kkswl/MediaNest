# 受控子目录索引交付（2026-10-25）

本轮仅处理待确认作品隔离、海报优先级和受控子目录索引。沿用现有技术栈，未提交、暂存或推送 Git；未启动子代理或并行验证 worker。开始时已有的未提交改动均保留，不把整个 Git diff 计为本轮新增代码。

## 变更文件和业务证据

| 文件 | 本轮改动 |
| --- | --- |
| `app/catalog.py` | 公开作品统一要求 confirmed、visible、存在可用版本；使用统一海报序列化 |
| `app/main.py` | 统计仅计公开作品；新增所有权隔离的指定目录索引接口；搜索不自动安排真实健康读取；人工海报校验和锁定 |
| `app/posters.py`（新增） | 海报候选证据、优先级、白名单校验、保守兼容旧海报、同目录多作品防误绑 |
| `app/identify_impl.py`、`app/identify_fixed2.py` | 接入 NFO、外部及目录海报证据，不因已有外部图而跳过源图 |
| `app/db.py` | schema v3 追加范围、请求预算、成功页数和节点数 |
| `app/scan_scope.py`（新增） | 验证目录归属、类型、完整祖先路径，固定任务范围和唯一扫描标识 |
| `app/worker.py` | 先持久化预留预算，最多两次目录请求；验证范围，不递归；保留租约 fence；仅模拟来源安排识别 |
| `frontend/src/components/SourceTree.vue` | 只读缓存树，显式“索引此目录”，向上冒泡选中节点 |
| `frontend/src/pages/Admin.vue` | 确认范围、预算说明、错误与取消反馈；限定完成/截断提示；待确认仅后台；未修改自动海报不误加人工锁 |
| `frontend/src/api.ts`、`frontend/src/components/Poster.vue`、`frontend/src/pages/Detail.vue` | 状态与海报来源标签，采用服务端选出的主图和备用图 |
| `tests/test_publish_barrier.py`（新增） | 公开列表、搜索、详情、演员、合集、统计、建议权限和确认/撤回/隐藏闭环 |
| `tests/test_posters.py`（新增） | NFO/目录/外部优先级、人工锁、真实识别函数接线、非法 URL、旧数据和多作品目录 |
| `tests/test_directory_scope.py`（新增） | 越权/类型/路径/循环/伪造、请求预算、暂停/重启/崩溃/重试、旧 worker 成功及失败隔离、不完整分页、迁移和从空库识别多版本 |
| `frontend/tests/interface.spec.ts` | 单 worker 桌面/移动模拟测试，外网请求拦截；明确范围确认、取消、统计展示和审核海报不误锁 |
| `docs/ARCHITECTURE.md`、`docs/VERIFICATION.md`、本文 | 更新架构、证据边界、交付和回滚说明 |

现有项目没有关联推荐接口；未新建另一个绕过公开门槛的查询。后台审核队列仍可查看 review 作品，公开 `review` 统计字段保留但返回 0。

## 数据迁移和 API 兼容

启动初始化或 `python -m app.cli migrate` 执行幂等的 schema v3：jobs 追加 scope_node_id、scope_remote_id、scope_path、scan_requests、pages_read、nodes_read。没有删除或重建既有表、作品、来源。旧任务 payload 的已用请求预算由 worker 取较大值继承，不会因为新列默认为 0 而恢复额度。

新接口：`POST /api/admin/sources/{source_id}/directories/{node_id}/scan`，JSON 请求体为空对象，登录和 CSRF 沿用现有约束。只接受自己来源中已记录且祖先路径完整的目录；来源停用或已有其他范围任务时拒绝。返回 job_id、scan_mode=directory_preview、scope_path、request_limit=2、recursive=false。同一活跃范围重复提交返回现有 job，不额外建任务。

任务列表保留旧字段，增加范围、页数、节点数；scan_requests 是网络调用前已提交的预留数，包括失败和崩溃，pages_read/nodes_read 仅计成功提交结果。complete 只表示限定任务结束，truncated=true 仍表示有未读取内容。根预览和指定目录是不同模式，不能靠 LIVE_ROOT_ONLY=no 绕开边界。

作品海报保留 info.poster/fallback_poster，增加 poster_candidates、poster_source、poster_locked、fallback_poster_source。候选优先级为人工锁定 > NFO > 作品目录 > 外部；旧无标记数据保留 legacy_unknown，不擅自升级为人工指定。所有候选和旧图字段重新校验，服务器不获取图片。普通访客仍只能建议修改，经管理员采纳后才锁定。

## 验证命令与结果

修改前：pytest 53 passed、2 warnings；ruff、build、生产依赖 audit、compose config、diff check 全部通过。

修改后串行执行：

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check --no-cache app tests scripts
npm --prefix frontend run build
npm --prefix frontend audit --omit=dev
docker compose config --quiet
git diff --check
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm --prefix frontend run test:e2e -- interface.spec.ts --workers=1
```

本轮验收结果见 `VERIFICATION.md` 顶部；只有命令实际通过后才能认定通过。audit 只涵盖生产依赖，不等于全部开发依赖都通过审计。Compose 配置通过不代表镜像构建或容器运行成功。

两条既有 Python 警告分别是 Starlette/httpx TestClient 弃用，以及 httpx raw upload 的 content 参数弃用。Git 可能提示 LF/CRLF 转换，但空白检查退出码为 0。Chrome 测试有 NO_COLOR/FORCE_COLOR 环境警告。

模拟 Python 集成覆盖真实应用的路由、数据库、claim、worker、识别函数；以虚构 demo 目录从空作品库创建一个作品并合并 MKV/ISO 两版本。模拟 live 分页证明指定目录至多两次请求、四个返回节点、不进入子目录、不读取 NFO、不调用 TMDB。它不证明真实 115 接口可用。

浏览器使用本机 Chrome，所有 API 均为测试模拟，非 loopback HTTP 请求被拦截；不启动真实后端或 115 worker。覆盖桌面和手机（确认页包括 375px）、加载/错误/取消/成功、审核、海报标签、限定状态和无页面横向溢出。新目录操作保持至少 44px 触控高度；截图保存在忽略的 frontend/test-results 中，未覆盖此前用户截图。

## 本轮真实调用与未验证能力

真实 115 请求 0 次，真实健康请求 0 次，真实 TMDB 请求 0 次；未读取 Cookie，没有新增真实分享或临时真实验证进程，无真实来源数据需要清理。本轮缺少完整的“唯一来源 + 指定目录节点 + 目录/健康请求上限”新授权，不复用之前的真实分享验证。

尚未验证真实子目录字段与分页、真实源图公开可访问性、真实 NFO、TMDB 匹配、长期限流与大规模扫描、PostgreSQL 长期/跨主机并发、容器构建及公网部署。未运行需要独立本地 API 的 local-integration.spec.ts；本轮浏览器证据是模拟 API，不能当成全栈浏览器验收。项目现有 loopback Host 边界未作公网部署改造。

## 保留原有改动的回滚方法

本轮开始时，拟编辑文件的逐文件副本保存在：

`G:\拆分115大包\data\development-backups\scope-poster-20261025`

该目录被现有 data/ 忽略规则排除，保存的是本轮开始时的脏工作区内容，不是 HEAD。未复制生产数据库或读取其凭据；本轮迁移测试只操作临时数据库。

回滚时先停止相关服务并备份当前源码、数据库和密钥，然后逐文件比较该副本与当前文件，用反向补丁仅撤销本轮变更。如果回滚前又产生新的用户修改，必须按 hunk 合并，不能整文件替换。禁止 git reset、clean、restore 整仓或删除原有未跟踪文件。

仅本轮新增文件为 app/posters.py、app/scan_scope.py、三个新增 test 文件和本文；确认没有后续引用后可移到单独归档目录，不要删除此前的 tests/test_public_scope.py、scripts/verify_public.py 或既有截图。数据库 v3 的附加列可留给旧代码，不自动 DROP、降级、重建或清空数据；生产回退只能使用用户自行确认的数据库备份。回滚后重新运行上述验证。
