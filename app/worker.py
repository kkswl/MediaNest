import time, uuid
from sqlalchemy import func, or_, select, update
from .adapters import ReadError, access_failure
from .db import Job, Node, Source, Task
from .health import record_health
from .metadata import TMDB, identify_directory, media_nodes
from .scan_scope import validate_directory_task


def start_scan(db, source, scan_mode=None):
    active = db.scalar(
        select(Job).where(Job.source_id == source.id, Job.status.in_(["queued", "running", "paused"]))
    )
    if active:
        if active.scan_mode == "directory_preview":
            raise ValueError("已有指定目录任务，请先完成或取消后再预览根目录")
        return active
    job = Job(source_id=source.id, owner_id=source.owner_id,
              scan_mode=scan_mode or ("root_preview" if source.adapter == "live" else "full"))
    db.add(job)
    db.flush()
    db.add(
        Task(
            job_id=job.id,
            source_id=source.id,
            kind="scan",
            target="0",
            dedupe_key=f"job:{job.id}:scan:0",
            payload={"offset": 0, "path": ""},
        )
    )
    return job


class Worker:
    def __init__(self, database, settings, readers, *, job_id=None, task_id=None):
        self.database, self.settings, self.readers, self.tmdb = database, settings, readers, TMDB(settings)
        self.job_id, self.task_id = job_id, task_id

    def bounded(self, source, job):
        return ((source.adapter == "live" and self.settings.live_root_only)
                or (job is not None and job.scan_mode in ("root_preview", "directory_preview")))

    def claim(self, ignore_schedule=False):
        now = time.time()
        with self.database.session.begin() as db:
            expired = update(Task).where(Task.status == "running", Task.lease_until < now)
            if self.job_id is not None:
                expired = expired.where(Task.job_id == self.job_id)
            if self.task_id is not None:
                expired = expired.where(Task.id == self.task_id)
            db.execute(expired.values(status="queued", lease_token=""))
            q = (
                select(Task)
                .join(Source, Source.id == Task.source_id)
                .outerjoin(Job, Job.id == Task.job_id)
                .where(
                    Task.status == "queued",
                    Source.enabled.is_(True),
                    or_(Task.job_id.is_(None), Job.status.in_(["queued", "running"])),
                )
            )
            if self.job_id is not None:
                q = q.where(Task.job_id == self.job_id)
            if self.task_id is not None:
                q = q.where(Task.id == self.task_id)
            q = (
                q.where(Source.adapter == "mock")
                if ignore_schedule
                else q.where(Task.available_at <= now, Source.next_request <= now)
            )
            task = db.scalar(q.order_by(Task.available_at, Task.id).limit(1))
            if not task:
                return None
            source = db.get(Source, task.source_id)
            job = db.get(Job, task.job_id) if task.job_id else None
            directory_preview = job is not None and job.scan_mode == "directory_preview"
            if directory_preview:
                try:
                    validate_directory_task(db, source, job, task)
                except ReadError:
                    task.status, task.error = "failed", "scope_limit: 指定目录授权校验失败"
                    job.status = "partial"
                    return None
            if self.bounded(source, job):
                allowed = directory_preview or ((task.kind == "scan" and task.target == "0") or
                                                 (task.kind == "health" and task.target == "root"))
                limit = 2 if task.kind == "scan" else 1
                requests = int(task.payload.get("requests", 0))
                if task.kind == "scan" and job:
                    # Legacy task budgets are carried forward, never reset by migration.
                    persisted = sum(int(t.payload.get("requests", 0)) for t in db.scalars(
                        select(Task).where(Task.job_id == job.id, Task.kind == "scan")))
                    requests = max(job.scan_requests, persisted)
                network_task = task.kind in ("scan", "health")
                if not allowed or (network_task and requests >= limit):
                    task.status, task.error = "failed", "scope_limit: 受控只读范围或请求预算已限制"
                    if job:
                        job.status = "partial"
                    return None
            lease = uuid.uuid4().hex
            if (
                db.execute(
                    update(Task)
                    .where(Task.id == task.id, Task.status == "queued")
                    .values(
                        status="running",
                        lease_until=now + self.settings.task_lease,
                        lease_token=lease,
                        attempts=Task.attempts + 1,
                        updated_at=now,
                    )
                ).rowcount
                != 1
            ):
                return None
            cond = [Source.id == task.source_id]
            if not ignore_schedule:
                cond.append(Source.next_request <= now)
            if (
                db.execute(
                    update(Source).where(*cond).values(next_request=now + self.settings.interval)
                ).rowcount
                != 1
            ):
                db.execute(update(Task).where(Task.id == task.id).values(status="queued", lease_token=""))
                return None
            if task.job_id:
                db.get(Job, task.job_id).status = "running"
            if self.bounded(source, job) and task.kind in ("scan", "health"):
                # Reserve before I/O: crashes and retries cannot reset the request budget.
                if task.kind == "scan" and job:
                    changed = db.execute(update(Job).where(Job.id == job.id, Job.scan_requests < 2,
                                                          Job.scan_requests == job.scan_requests)
                                         .values(scan_requests=requests + 1))
                    if changed.rowcount != 1:
                        task.status, task.lease_token = "failed", ""
                        task.error, job.status = "scope_limit: 请求预算耗尽", "partial"
                        return None
                task.payload = dict(task.payload, requests=requests + 1)
            return task.id, lease

    def tick(self, ignore_schedule=False):
        claimed = self.claim(ignore_schedule)
        if not claimed:
            return False
        tid, lease = claimed
        with self.database.session() as db:
            task = db.get(Task, tid)
            jid = task.job_id
            source = db.get(Source, task.source_id)
            try:
                job = db.get(Job, jid) if jid else None
                if job and job.scan_mode == "directory_preview":
                    validate_directory_task(db, source, job, task)
                if task.kind == "scan":
                    self.scan(db, task, source)
                elif task.kind == "identify":
                    self.discover_media(db, task, source)
                elif task.kind == "identify_media":
                    identify_directory(
                        db,
                        source,
                        str(task.payload.get("directory", "0")),
                        self.readers,
                        self.tmdb,
                        media_node_id=int(task.target),
                        local_only=source.adapter == "live" and self.bounded(source, job),
                    )
                    task.status = "done"
                elif task.kind == "health":
                    self.health(db, task, source)
                with db.no_autoflush:
                    fenced = db.execute(
                        update(Task)
                        .where(Task.id == tid, Task.lease_token == lease, Task.lease_until >= time.time(),
                               Task.status != "cancelled")
                        .values(updated_at=time.time())
                        .execution_options(synchronize_session=False)
                    )
                if fenced.rowcount != 1:
                    db.rollback()
                    return True
                task.lease_token = ""
                task.lease_until = 0
                db.commit()
            except Exception as exc:
                db.rollback()
                task = db.get(Task, tid)
                if not task or task.lease_token != lease or task.status != "running" or task.lease_until < time.time():
                    return True
                kind = exc.kind if isinstance(exc, ReadError) else "internal"
                category = "auth_failed" if kind == "auth" else kind
                task.error = f"{category}: 读取未完成，未判定资源不存在" if isinstance(exc, ReadError) else "internal: 任务执行异常"
                if kind == "missing":
                    task.error = "missing: 目录接口明确返回不存在，按连续失败规则复检"
                source = db.get(Source, task.source_id)
                access_failure(source, kind)
                if task.kind == "scan" and isinstance(exc, ReadError):
                    # Scan errors are health evidence too. A missing directory
                    # must NOT mark the whole share missing.
                    node = None if task.target == "0" else db.scalar(select(Node).where(
                        Node.source_id == source.id, Node.remote_id == task.target))
                    if task.target == "0" or node is not None:
                        record_health(db, source, node, kind, "目录扫描未完成（脱敏分类）", self.settings)
                bounded = self.bounded(source, db.get(Job, jid) if jid else None)
                limit = 2 if task.kind == "scan" else 1
                within_budget = not bounded or int(task.payload.get("requests", 0)) < limit
                if kind in ("timeout", "rate_limited", "uncertain", "network_error", "incomplete") and task.attempts < 4 and within_budget:
                    task.status = "queued"
                    task.available_at = time.time() + min(300, 2**task.attempts)
                    if kind == "rate_limited":
                        source.next_request = max(source.next_request, task.available_at)
                else:
                    task.status = "failed"
                    task.dedupe_key = None if task.kind == "health" else task.dedupe_key
                task.lease_token = ""
                task.lease_until = 0
                db.commit()
        if jid:
            self.refresh_job(jid)
        return True

    def refresh_job(self, jid):
        with self.database.session.begin() as db:
            job = db.get(Job, jid)
            if not job or job.status in ("paused", "cancelled"):
                return
            c = dict(
                db.execute(
                    select(Task.status, func.count()).where(Task.job_id == jid).group_by(Task.status)
                ).all()
            )
            if c.get("queued", 0) + c.get("running", 0) == 0:
                job.status = "partial" if c.get("failed", 0) else "complete"
                job.finished_at = time.time()
                db.get(Source, job.source_id).last_scan = time.time()

    def scan(self, db, task, source):
        p = dict(task.payload)
        off = int(p.get("offset", 0))
        job = db.get(Job, task.job_id) if task.job_id else None
        directory_preview = job is not None and job.scan_mode == "directory_preview"
        bounded = self.bounded(source, job)
        if directory_preview:
            validate_directory_task(db, source, job, task)
        if bounded and ((not directory_preview and task.target != "0") or int(p.get("requests", 0)) > 2):
            raise ReadError("scope_limit", "超过根目录验证范围")
        items, total = self.readers.page(source, task.target, off, self.settings.page_size)
        if total < 0 or len(items) > max(0, total - off) or (not items and off < total):
            raise ReadError("incomplete", "分页未完整返回")
        if off and p.get("total") != total:
            if bounded:
                raise ReadError("incomplete", "目录总数变化，停止验证")
            task.payload = dict(p, offset=0)
            task.status = "queued"
            return
        if bounded:
            remote_ids = [item["id"] for item in items]
            if len(set(remote_ids)) != len(remote_ids) or set(remote_ids).intersection(p.get("seen", [])):
                raise ReadError("incomplete", "分页存在重复节点")
            for item in items:
                name = item["name"]
                if (not name or name in (".", "..") or "/" in name or "\\" in name
                        or item["id"] == task.target or any(ord(c) < 32 for c in name)):
                    raise ReadError("incomplete", "目录节点路径不完整")
            p["seen"] = list(p.get("seen", [])) + remote_ids
        now = time.time()
        for item in items:
            node = db.scalar(select(Node).where(Node.source_id == source.id, Node.remote_id == item["id"]))
            if (directory_preview and node and node.is_dir and
                    job.scope_path.startswith(node.path + "/")):
                raise ReadError("incomplete", "分页返回了当前范围的祖先节点")
            path = "/".join(x for x in (p.get("path", ""), item["name"]) if x)
            if not node:
                node = Node(
                    source_id=source.id,
                    remote_id=item["id"],
                    parent_remote_id=task.target,
                    name=item["name"],
                    path=path,
                    is_dir=item["is_dir"],
                )
                db.add(node)
            node.name, node.path, node.parent_remote_id = item["name"], path, task.target
            node.is_dir = item["is_dir"]
            node.size, node.sha1, node.public_image = (
                item.get("size", 0),
                item.get("sha1", ""),
                item.get("public_image", ""),
            )
            node.health, node.failures, node.checked_at, node.last_scan = "healthy", 0, now, now
            if node.is_dir and not bounded:
                key = f"job:{task.job_id}:scan:{node.remote_id}"
                if not db.scalar(select(Task.id).where(Task.dedupe_key == key)):
                    db.add(
                        Task(
                            job_id=task.job_id,
                            source_id=source.id,
                            kind="scan",
                            target=node.remote_id,
                            dedupe_key=key,
                            payload={"offset": 0, "path": path},
                        )
                    )
        if task.target == "0" and off == 0:
            record_health(db, source, None, "healthy", "分享目录读取成功", self.settings)
        elif directory_preview and off == 0:
            record_health(db, source, db.get(Node, job.scope_node_id), "healthy", "指定目录可读取", self.settings)
        nxt = off + len(items)
        p.update(offset=nxt, total=total)
        task.payload = p
        if bounded:
            if job:
                job.pages_read += 1
                job.nodes_read += len(items)
            p["truncated"] = nxt < total
            task.payload = p
            task.status = "done" if nxt >= total or int(p.get("requests", 0)) >= 2 else "queued"
            task.available_at = now + self.settings.interval
            if task.status == "done" and directory_preview:
                actual_media = media_nodes(source.id, task.target).where(Node.remote_id.in_(p.get("seen", [])))
                if db.scalar(actual_media.limit(1)):
                    db.add(Task(job_id=job.id, source_id=source.id, kind="identify", target=task.target,
                                dedupe_key=f"job:{job.id}:identify:{task.target}", payload={"cursor": 0}))
            return
        if nxt < total:
            task.status = "queued"
            task.available_at = now + self.settings.interval
        else:
            task.status = "done"
            key = f"job:{task.job_id}:identify:{task.target}"
            if not db.scalar(select(Task.id).where(Task.dedupe_key == key)):
                db.add(
                    Task(
                        job_id=task.job_id,
                        source_id=source.id,
                        kind="identify",
                        target=task.target,
                        dedupe_key=key,
                        payload={"cursor": 0},
                    )
                )

    def discover_media(self, db, task, source):
        cur = int(task.payload.get("cursor", 0))
        query = media_nodes(source.id, task.target).where(Node.id > cur)
        job = db.get(Job, task.job_id) if task.job_id else None
        if job and job.scan_mode == "directory_preview":
            scan = db.scalar(select(Task).where(Task.job_id == job.id, Task.kind == "scan"))
            query = query.where(Node.remote_id.in_(scan.payload.get("seen", [])))
        vals = db.scalars(query.order_by(Node.id).limit(25)).all()
        for n in vals:
            key = f"job:{task.job_id}:identify_media:{n.id}"
            if not db.scalar(select(Task.id).where(Task.dedupe_key == key)):
                db.add(
                    Task(
                        job_id=task.job_id,
                        source_id=source.id,
                        kind="identify_media",
                        target=str(n.id),
                        dedupe_key=key,
                        payload={"directory": task.target},
                    )
                )
        if vals:
            task.payload = {"cursor": vals[-1].id}
            task.status = "queued"
            task.available_at = time.time() + self.settings.interval
        else:
            task.status = "done"

    def health(self, db, task, source):
        node = db.get(Node, int(task.target)) if task.target != "root" else None
        if task.target != "root" and (not node or node.source_id != source.id):
            raise ReadError("internal", "节点不属于来源")
        p = dict(task.payload)
        directory = node.parent_remote_id if node else "0"
        off = p.get("offset", 0)
        try:
            items, total = self.readers.page(source, directory, off, self.settings.page_size)
            if total < 0 or len(items) > max(0, total - off) or (not items and off < total):
                result, reason = "incomplete", "分页响应不完整"
            elif not node:
                result, reason = "healthy", "分享入口可读"
            elif off and p.get("total") != total:
                result, reason = "uncertain", "目录变化"
            elif any(x["id"] == node.remote_id for x in items):
                result, reason = "healthy", "找到节点 ID"
            elif off + len(items) < total:
                task.payload = {"offset": off + len(items), "total": total}
                task.status = "queued"
                task.available_at = time.time() + self.settings.interval
                return
            else:
                result, reason = "missing", "父目录完整读取后未找到节点"
        except ReadError as exc:
            result, reason = exc.kind, "分享读取未完成"
        record_health(db, source, node, result, reason, self.settings)
        task.status = "done"
        task.dedupe_key = None
        target = node or source
        if target.health == "pending" and not self.bounded(source, db.get(Job, task.job_id) if task.job_id else None):
            db.flush()
            db.add(
                Task(
                    source_id=source.id,
                    kind="health",
                    target=task.target,
                    dedupe_key=f"health:{source.id}:{task.target}",
                    payload={"offset": 0},
                    available_at=time.time() + self.settings.recheck_delay,
                )
            )

    def drain(self, max_ticks=1000, ignore_schedule=True):
        i = 0
        while i < max_ticks and self.tick(ignore_schedule):
            i += 1
        return i
