import hmac
import re
import secrets
import time
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from .adapters import Readers
from .catalog import catalog_query, public_works, valid_variants, variant_dict, work_dict
from .config import Settings
from .db import (
    Admin,
    Audit,
    Collection,
    Database,
    HealthEvent,
    Job,
    Node,
    Person,
    SessionToken,
    Source,
    Suggestion,
    Task,
    Variant,
    Work,
    WorkCollection,
    WorkPerson,
)
from .health import enqueue_check
from .metadata import update_links
from .security import cipher, digest, parse_import, password_hash, password_valid, rate_limit, safe_url
from .worker import Worker, start_scan


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class ImportText(StrictModel):
    text: str = Field(min_length=1, max_length=100000)


class ImportItem(StrictModel):
    url: str = Field(max_length=2000)
    access_code: str = Field(default="", max_length=32, pattern=r"^[A-Za-z0-9]*$")
    title: str = Field(default="", max_length=500)


class ImportBatch(StrictModel):
    items: list[ImportItem] = Field(min_length=1, max_length=100)
    adapter: Literal["mock", "live"] = "mock"


class SourcePatch(StrictModel):
    title: str | None = Field(default=None, max_length=500)
    access_code: str | None = Field(default=None, max_length=100)
    enabled: bool | None = None
    credential: str | None = Field(default=None, max_length=10000)


class NewAdmin(StrictModel):
    username: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=200)
    superuser: bool = False


class AdminPatch(StrictModel):
    active: bool | None = None
    superuser: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=200)


class WorkPatch(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    year: int | None = Field(default=None, ge=1888, le=2100)
    category: Literal["movie", "tv", "anime", "variety", "concert"] | None = None
    status: Literal["confirmed", "review"] | None = None
    visible: bool | None = None
    poster: str | None = Field(default=None, max_length=2000)
    tmdb_url: str | None = Field(default=None, max_length=2000)
    plot: str | None = Field(default=None, max_length=10000)
    actors: list[str] | None = Field(default=None, max_length=100)
    genres: list[str] | None = Field(default=None, max_length=30)
    path: str | None = Field(default=None, max_length=4000)
    variant_id: int | None = None


class NewSuggestion(StrictModel):
    work_id: int
    changes: dict = Field(max_length=10)


class Review(StrictModel):
    accept: bool
    reason: str = Field(default="", max_length=1000)


class Recheck(StrictModel):
    source_id: int
    node_id: int | None = None


def source_dict(source, include_access=True):
    fields = ("id", "owner_id", "code", "url", "title", "adapter", "enabled", "health", "failures",
              "checked_at", "last_scan")
    result = {key: getattr(source, key) for key in fields}
    if include_access:
        result["access_code"] = source.access_code
    return result | {"has_credential": bool(source.credential)}


def redact_audit(value):
    """Remove secrets before an audit record is returned to another admin."""
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            if key in {"credential", "access_code", "password", "token", "cookie"}:
                output[key] = "[已隐藏]"
            elif key == "url" and isinstance(item, str):
                output[key] = re.sub(r"([?&]password=)[^&\s]+", r"\1[已隐藏]", item)
            else:
                output[key] = redact_audit(item)
        return output
    if isinstance(value, list):
        return [redact_audit(item) for item in value]
    return value


def create_app(settings=None):
    settings = settings or Settings()
    database = Database(settings.database_url)
    database.init()
    secret = settings.get_secret()
    readers = Readers(settings, secret)
    app = FastAPI(title="映集 · 只读分享索引", version="0.1.0")
    app.state.database, app.state.readers = database, readers
    app.state.settings = settings
    app.state.worker = Worker(database, settings, readers)

    def serialize_work(db, work):
        return work_dict(db, work, settings.public_image_hosts)

    image_origins = " ".join("https://" + host for host in settings.public_image_hosts
                             if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", host))

    @app.middleware("http")
    async def boundaries(request, call_next):
        host = request.url.hostname
        if host not in ("127.0.0.1", "localhost", "::1", "testserver"):
            return JSONResponse({"detail": "本地开发服务不接受该 Host"}, status_code=400)
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            origin = request.headers.get("origin")
            allowed = {f"http://{h}:{p}" for h in ("localhost", "127.0.0.1") for p in (8000, 5173, 4173)}
            allowed.add(str(request.base_url).rstrip("/"))
            if origin and origin not in allowed:
                return JSONResponse({"detail": "跨站写请求被拒绝"}, status_code=403)
            csrf_cookie = request.cookies.get("csrf_token", "")
            csrf_header = request.headers.get("x-csrf-token", "")
            # Same-origin browser writes include the double-submit token.  Keep
            # non-browser local TestClient/CLI callers usable when they omit an
            # Origin header; cross-site requests are already rejected above.
            if csrf_cookie and (origin or csrf_header) and not csrf_header:
                return JSONResponse({"detail": "缺少 CSRF 校验令牌"}, status_code=403)
            if csrf_cookie and csrf_header and not hmac.compare_digest(csrf_cookie, csrf_header):
                return JSONResponse({"detail": "CSRF 校验令牌无效"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "写请求仅接受 application/json"}, status_code=415)
            try:
                declared_size = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "无效请求长度"}, status_code=400)
            if declared_size < 0 or declared_size > 200000:
                return JSONResponse({"detail": "请求过大"}, status_code=413)
            collected = bytearray()
            async for chunk in request.stream():
                collected.extend(chunk)
                if len(collected) > 200000:
                    return JSONResponse({"detail": "请求过大"}, status_code=413)
            request._body = bytes(collected)
        result = await call_next(request)
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["Referrer-Policy"] = "no-referrer"
        result.headers["X-Frame-Options"] = "DENY"
        result.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data: https://image.tmdb.org "
              "https://img1.doubanio.com https://img2.doubanio.com https://img3.doubanio.com https://img9.doubanio.com "
              + image_origins + "; "
              "script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        if request.url.path.startswith("/api/"):
            result.headers["Cache-Control"] = "no-store"
        if not request.cookies.get("csrf_token"):
            result.set_cookie("csrf_token", secrets.token_urlsafe(32), httponly=False,
                              samesite="strict", secure=request.url.scheme == "https", path="/")
        return result

    @app.exception_handler(ValueError)
    async def invalid(_, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(IntegrityError)
    async def conflict(_, exc):
        return JSONResponse({"detail": "记录已存在或被其他操作更新，请刷新重试"}, status_code=409)

    def get_db():
        with database.session() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    # Commit before response headers/cookies become observable by the next request.
    # FastAPI's default request-scope yield teardown otherwise races browser /me.
    transaction = Depends(get_db, scope="function")

    def admin(request: Request, db=transaction):
        session = db.get(SessionToken, digest(request.cookies.get("yingji_session", "")))
        user = db.get(Admin, session.admin_id) if session and not session.revoked and session.expires > time.time() else None
        if not user or not user.active:
            raise HTTPException(401, "请先登录管理员")
        return user

    def own_source(db, source_id, user):
        source = db.get(Source, source_id)
        if not source or source.owner_id != user.id:
            raise HTTPException(404, "来源不存在或无权访问")
        return source

    def audit(db, user, action, target, before=None, after=None):
        db.add(Audit(admin_id=user.id, action=action, target=str(target), before=before or {}, after=after or {}))

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response, db=transaction):
        ip = request.client.host if request.client else "local"
        allowed = rate_limit(db, "login:" + digest(ip), limit=15, seconds=900)
        db.commit()
        if not allowed:
            raise HTTPException(429, "登录尝试过多，请稍后重试")
        user = db.scalar(select(Admin).where(Admin.username == body.username, Admin.active.is_(True)))
        if not user or not password_valid(body.password, user.password_hash):
            raise HTTPException(401, "用户名或密码错误")
        token = secrets.token_urlsafe(48)
        db.add(SessionToken(digest=digest(token), admin_id=user.id, expires=time.time() + 43200))
        response.set_cookie("yingji_session", token, httponly=True, samesite="strict", max_age=43200,
                            secure=request.url.scheme == "https", path="/")
        return {"id": user.id, "username": user.username, "superuser": user.superuser}

    @app.get("/api/me")
    def me(user=Depends(admin)):
        return {"id": user.id, "username": user.username, "superuser": user.superuser}

    @app.post("/api/logout")
    def logout(request: Request, response: Response, user=Depends(admin), db=transaction):
        token = db.get(SessionToken, digest(request.cookies.get("yingji_session", "")))
        if token:
            db.delete(token)
        response.delete_cookie("yingji_session", path="/")
        response.delete_cookie("csrf_token", path="/")
        return {"ok": True}

    @app.get("/api/stats")
    def stats(db=transaction):
        return {"works": db.scalar(select(func.count()).select_from(public_works().subquery())),
                "variants": db.scalar(select(func.count()).select_from(valid_variants().subquery())),
                "sources": db.scalar(select(func.count(Source.id)).where(Source.enabled.is_(True))),
                "review": db.scalar(select(func.count(Work.id)).where(Work.status == "review", Work.visible.is_(True))),
                "mock": not settings.live_enabled, "live_enabled": settings.live_enabled}

    @app.get("/api/catalog")
    def catalog(request: Request, q: str = Query("", max_length=200), category: str = Query("", max_length=30),
                year: int | None = None, resolution: str = Query("", max_length=30),
                language: str = Query("", max_length=30), subtitle: str = Query("", max_length=30),
                format: str = Query("", max_length=30), person: int | None = None, collection: int | None = None,
                genre: str = Query("", max_length=100), page: int = Query(1, ge=1),
                page_size: int = Query(24, ge=1, le=60), db=transaction):
        ip = request.client.host if request.client else "local"
        if not rate_limit(db, "catalog:" + digest(ip + secret), limit=120, seconds=60):
            raise HTTPException(429, "搜索请求过于频繁，请稍后再试")
        query = catalog_query(q, category, year, resolution, language, subtitle, format, person, collection, genre)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        works = db.scalars(query.order_by(Work.year.desc(), Work.id).offset((page - 1) * page_size).limit(page_size)).all()
        # Bounded asynchronous refresh: no network I/O on this route.
        for work in works:
            for v in db.scalars(valid_variants().where(Variant.work_id == work.id)
                                .order_by(Node.checked_at, Variant.id).limit(2)).all():
                source, node = db.get(Source, v.source_id), db.get(Node, v.node_id)
                enqueue_check(db, source, None, settings)
                enqueue_check(db, source, node, settings)
        return {"items": [serialize_work(db, w) for w in works], "total": total, "page": page, "page_size": page_size}

    @app.get("/api/works/{work_id}")
    def detail(work_id: int, db=transaction):
        work = db.scalar(public_works().where(Work.id == work_id))
        if not work:
            raise HTTPException(404, "作品不存在或暂无可展示来源")
        variants = db.scalars(valid_variants().where(Variant.work_id == work_id).order_by(Variant.season, Variant.id)).all()
        return serialize_work(db, work) | {"variants": [variant_dict(db, v, work) for v in variants]}

    @app.get("/api/people")
    def people(db=transaction):
        visible = public_works().with_only_columns(Work.id)
        rows = db.execute(select(Person.id, Person.name, func.count(WorkPerson.work_id)).join(WorkPerson).where(
            WorkPerson.work_id.in_(visible)).group_by(Person.id, Person.name).order_by(Person.name)).all()
        return {"items": [{"id": r[0], "name": r[1], "count": r[2]} for r in rows]}

    @app.get("/api/collections")
    def collections(db=transaction):
        visible = public_works().with_only_columns(Work.id)
        rows = db.execute(select(Collection.id, Collection.name, Collection.kind, func.count(WorkCollection.work_id))
                          .join(WorkCollection).where(WorkCollection.work_id.in_(visible))
                          .group_by(Collection.id, Collection.name, Collection.kind).order_by(Collection.name)).all()
        return {"items": [{"id": r[0], "name": r[1], "kind": r[2], "count": r[3]} for r in rows]}

    def validate_changes(changes, work, db, public=False):
        allowed = {"title", "year", "poster", "tmdb_url", "path", "variant_id"}
        if public and set(changes) - allowed:
            raise ValueError("访客仅可建议片名、年份、海报、TMDB 及指定版本路径")
        validated = WorkPatch.model_validate(changes).model_dump(exclude_unset=True)
        if any(validated.get(k) is None for k in ("title", "category", "status", "visible") if k in validated):
            raise ValueError("片名、类别、状态及可见性不能设为空")
        if "poster" in validated:
            validated["poster"] = safe_url(validated["poster"] or "", image=True)
        if "tmdb_url" in validated:
            validated["tmdb_url"] = safe_url(validated["tmdb_url"] or "", tmdb=True)
        if "path" in validated:
            path = validated["path"]
            if not path or path.startswith(("/", "\\")) or any(x == ".." for x in re.split(r"[/\\]", path)):
                raise ValueError("请输入无上级跳转的完整相对路径")
            variant = db.get(Variant, validated.get("variant_id")) if validated.get("variant_id") else None
            if not variant or variant.work_id != work.id:
                raise ValueError("目录纠错必须指定该作品下的版本 variant_id")
        for key in ("title", "plot"):
            if key in validated and validated[key] and re.search(r"[<>\x00-\x08]", validated[key]):
                raise ValueError("字段不接受 HTML 或控制字符")
        if not any(k != "variant_id" for k in validated):
            raise ValueError("建议内容不能为空")
        return validated

    def apply_changes(db, work, changes):
        info, provenance, locked = dict(work.info), dict(work.provenance), set(work.locked)
        for key, value in changes.items():
            if key in ("title", "year", "category", "status", "visible"):
                setattr(work, key, value)
            elif key == "path":
                overrides = dict(info.get("path_overrides", {}))
                overrides[str(changes["variant_id"])] = value
                info["path_overrides"] = overrides
            elif key != "variant_id":
                info[key] = value
            provenance[key] = "管理员审核"
            locked.add(key)
        work.info, work.provenance, work.locked, work.updated_at = info, provenance, sorted(locked), time.time()
        update_links(db, work)

    @app.post("/api/suggestions", status_code=201)
    def suggest(body: NewSuggestion, request: Request, db=transaction):
        work = db.scalar(public_works().where(Work.id == body.work_id))
        if not work:
            raise HTTPException(404, "作品不可公开访问")
        changes = validate_changes(body.changes, work, db, public=True)
        ip = request.client.host if request.client else "local"
        if not rate_limit(db, "suggest:" + digest(ip + secret)):
            raise HTTPException(429, "提交过于频繁，请稍后再试")
        pending = db.scalars(select(Suggestion).where(Suggestion.work_id == work.id, Suggestion.status == "pending")).all()
        if any(s.changes == changes for s in pending):
            raise HTTPException(409, "相同建议正在审核")
        suggestion = Suggestion(work_id=work.id, changes=changes)
        db.add(suggestion)
        db.flush()
        return {"id": suggestion.id, "status": "pending", "message": "已提交，审核后生效"}

    @app.get("/api/admin/sources")
    def sources(user=Depends(admin), db=transaction):
        return {"items": [source_dict(s) for s in db.scalars(select(Source).where(Source.owner_id == user.id)).all()]}

    @app.post("/api/admin/import/preview")
    def preview(body: ImportText, user=Depends(admin)):
        return {"items": parse_import(body.text)}

    @app.post("/api/admin/import", status_code=201)
    def import_batch(body: ImportBatch, user=Depends(admin), db=transaction):
        if body.adapter == "live" and not settings.live_enabled:
            raise HTTPException(403, "真实 115 读取尚未授权，当前仅可导入模拟来源")
        result = []
        for item in body.items:
            parsed_items = parse_import(item.url)
            if len(parsed_items) != 1:
                raise ValueError("每条导入项必须只包含一个分享链接")
            parsed = parsed_items[0]
            if parsed.get("conflict"):
                raise ValueError(f"分享 {parsed['code']} 的访问码存在冲突，请在预览中修正")
            access_code = item.access_code or parsed["access_code"]
            if not access_code:
                raise ValueError(f"分享 {parsed['code']} 缺少访问码")
            if not re.fullmatch(r"[A-Za-z0-9]{1,32}", access_code):
                raise ValueError(f"分享 {parsed['code']} 的访问码格式无效")
            if item.access_code and parsed["access_code"] and item.access_code != parsed["access_code"]:
                raise ValueError(f"分享 {parsed['code']} 的手填访问码与链接不一致")
            if body.adapter == "mock" and parsed["code"] not in ("demoa", "demob", "demotv"):
                raise ValueError("模拟模式仅接受 demoa、demob、demotv，不处理真实分享")
            source = db.scalar(select(Source).where(Source.owner_id == user.id, Source.code == parsed["code"]))
            if not source:
                source = Source(owner_id=user.id, code=parsed["code"], access_code=access_code,
                                url=parsed["url"], title=item.title or parsed["code"], adapter=body.adapter)
                db.add(source)
                db.flush()
            else:
                source.access_code = access_code
                source.url = parsed["url"]
                if item.title:
                    source.title = item.title
            job = start_scan(db, source)
            result.append(source_dict(source) | {"job_id": job.id})
            audit(db, user, "import", source.id, after={"job_id": job.id, "adapter": source.adapter})
        return {"items": result}

    @app.patch("/api/admin/sources/{source_id}")
    def patch_source(source_id: int, body: SourcePatch, user=Depends(admin), db=transaction):
        source = own_source(db, source_id, user)
        before = source_dict(source, include_access=False)
        for key, value in body.model_dump(exclude_unset=True).items():
            if value is None:
                continue
            setattr(source, key, cipher(secret).encrypt(value.encode()).decode() if key == "credential" and value else value)
        audit(db, user, "source.update", source.id, before, source_dict(source, include_access=False))
        return source_dict(source)

    @app.post("/api/admin/sources/{source_id}/scan")
    def scan_source(source_id: int, user=Depends(admin), db=transaction):
        source = own_source(db, source_id, user)
        if not source.enabled:
            raise ValueError("来源已停用")
        job = start_scan(db, source)
        return {"job_id": job.id}

    @app.get("/api/admin/sources/{source_id}/nodes")
    def nodes(source_id: int, parent: str = "0", page: int = Query(1, ge=1), refresh: bool = False,
              user=Depends(admin), db=transaction):
        source = own_source(db, source_id, user)
        scan_pending = False
        if refresh:
            existing = db.scalar(select(Node.id).where(Node.source_id == source_id,
                                                        Node.parent_remote_id == parent))
            if existing is None:
                active = db.scalar(select(Job).where(Job.source_id == source_id,
                                                     Job.status.in_(["queued", "running", "paused"])))
                if active is None:
                    active = Job(source_id=source.id, owner_id=user.id)
                    db.add(active)
                    db.flush()
                if parent == "0":
                    key = f"job:{active.id}:scan:0"
                    payload = {"offset": 0, "path": ""}
                else:
                    parent_node = db.scalar(select(Node).where(Node.source_id == source_id,
                                                               Node.remote_id == parent))
                    if not parent_node:
                        raise HTTPException(404, "父目录尚未建立索引")
                    key = f"job:{active.id}:scan:{parent}"
                    payload = {"offset": 0, "path": parent_node.path}
                if not db.scalar(select(Task.id).where(Task.dedupe_key == key)):
                    db.add(Task(job_id=active.id, source_id=source_id, kind="scan", target=parent,
                                dedupe_key=key, payload=payload))
                scan_pending = True
        query = select(Node).where(Node.source_id == source_id, Node.parent_remote_id == parent)
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        values = db.scalars(query.order_by(Node.is_dir.desc(), Node.name).offset((page - 1) * 100).limit(100)).all()
        return {"items": [{k: getattr(n, k) for k in ("id", "remote_id", "parent_remote_id", "name", "path", "is_dir",
                         "size", "health", "failures", "checked_at", "last_scan")} for n in values],
                "total": total, "page": page, "page_size": 100, "scan_pending": scan_pending}

    @app.get("/api/admin/jobs")
    def jobs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), user=Depends(admin), db=transaction):
        base = select(Job).where(Job.owner_id == user.id)
        total = db.scalar(select(func.count()).select_from(base.subquery()))
        rows = db.scalars(base.order_by(Job.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
        output = []
        for job in rows:
            counts = dict(db.execute(select(Task.status, func.count()).where(Task.job_id == job.id).group_by(Task.status)).all())
            source = db.get(Source, job.source_id)
            failed = db.scalars(select(Task).where(Task.job_id == job.id, Task.status == "failed").limit(20)).all()
            output.append({"id": job.id, "source_id": job.source_id, "title": source.title, "status": job.status,
                           "created_at": job.created_at, "finished_at": job.finished_at,
                           "total": sum(counts.values()), "done": counts.get("done", 0),
                           "failed": counts.get("failed", 0), "queued": counts.get("queued", 0),
                           "running": counts.get("running", 0), "cancelled": counts.get("cancelled", 0),
                           "errors": [{"id": t.id, "target": t.target, "error": t.error, "payload": t.payload} for t in failed]})
        return {"items": output, "total": total, "page": page, "page_size": page_size}

    @app.post("/api/admin/jobs/{job_id}/{action}")
    def job_action(job_id: int, action: Literal["pause", "resume", "retry", "cancel"], user=Depends(admin), db=transaction):
        job = db.get(Job, job_id)
        if not job or job.owner_id != user.id:
            raise HTTPException(404, "任务不存在")
        if action == "pause" and job.status in ("queued", "running"):
            job.status = "paused"
        elif action == "resume" and job.status == "paused":
            job.status = "queued"
            active = db.scalar(select(Task.id).where(Task.job_id == job.id,
                                                     Task.status.in_(["queued", "running"])))
            if not active:
                failed = db.scalar(select(Task.id).where(Task.job_id == job.id, Task.status == "failed"))
                job.status = "partial" if failed else "complete"
                job.finished_at = time.time()
            active = db.scalar(select(Task.id).where(Task.job_id == job.id, Task.status.in_(["queued", "running"])))
            if not active:
                failed = db.scalar(select(Task.id).where(Task.job_id == job.id, Task.status == "failed"))
                job.status = "partial" if failed else "complete"
                job.finished_at = time.time()
        elif action == "retry" and job.status in ("partial", "complete"):
            retried = db.execute(update(Task).where(Task.job_id == job.id, Task.status == "failed")
                       .values(status="queued", available_at=0, attempts=0, error=""))
            if not retried.rowcount:
                raise HTTPException(409, "没有失败任务需要重试")
            job.status, job.finished_at = "queued", None
        elif action == "cancel" and job.status not in ("complete", "cancelled"):
            job.status = "cancelled"
            db.execute(update(Task).where(Task.job_id == job.id, Task.status.in_(["queued", "running"]))
                       .values(status="cancelled", lease_until=0, lease_token="", updated_at=time.time(),
                               error="任务由管理员取消"))
            db.execute(update(Task).where(Task.job_id == job.id, Task.status.in_(["queued", "running"]))
                       .values(status="cancelled", lease_until=0, lease_token="", updated_at=time.time(),
                               error="任务由管理员取消"))
        else:
            raise HTTPException(409, "任务当前状态不允许此操作")
        audit(db, user, "job." + action, job_id)
        return {"id": job.id, "status": job.status}

    @app.get("/api/admin/review")
    def review_queue(user=Depends(admin), db=transaction):
        rows = db.scalars(select(Work).where(Work.status == "review").order_by(Work.id.desc()).limit(200)).all()
        output = []
        for work in rows:
            item = serialize_work(db, work)
            variants = db.scalars(select(Variant).where(Variant.work_id == work.id)).all()
            item["variants"] = [{"id": v.id, "path": db.get(Node, v.node_id).path,
                                 "source_title": db.get(Source, v.source_id).title} for v in variants]
            output.append(item)
        return {"items": output}

    @app.patch("/api/admin/works/{work_id}")
    def patch_work(work_id: int, body: WorkPatch, user=Depends(admin), db=transaction):
        work = db.get(Work, work_id)
        if not work:
            raise HTTPException(404, "作品不存在")
        changes = validate_changes(body.model_dump(exclude_unset=True), work, db)
        before = serialize_work(db, work)
        apply_changes(db, work, changes)
        audit(db, user, "work.update", work.id, before, changes)
        return serialize_work(db, work)

    @app.get("/api/admin/health/targets")
    def unhealthy(user=Depends(admin), db=transaction):
        output = []
        for source in db.scalars(select(Source).where(Source.owner_id == user.id)).all():
            if source.health != "healthy":
                output.append({"scope": "share", "id": source.id, "source_id": source.id, "path": source.title,
                               "health": source.health, "failures": source.failures})
            for n in db.scalars(select(Node).where(Node.source_id == source.id, Node.health != "healthy").limit(200)).all():
                output.append({"scope": "directory" if n.is_dir else "file", "id": n.id, "node_id": n.id,
                               "source_id": source.id, "path": n.path, "health": n.health, "failures": n.failures})
        return {"items": output}

    @app.get("/api/admin/health")
    def health_history(user=Depends(admin), db=transaction):
        rows = db.scalars(select(HealthEvent).join(Source).where(Source.owner_id == user.id)
                          .order_by(HealthEvent.id.desc()).limit(300)).all()
        return {"items": [{"id": x.id, "source_id": x.source_id, "node_id": x.node_id, "result": x.result,
                           "state": x.state, "reason": x.reason, "at": x.at,
                           "source_title": db.get(Source, x.source_id).title,
                           "path": db.get(Node, x.node_id).path if x.node_id else "/"} for x in rows]}

    @app.post("/api/admin/recheck")
    def recheck(body: Recheck, user=Depends(admin), db=transaction):
        source = own_source(db, body.source_id, user)
        node = db.get(Node, body.node_id) if body.node_id else None
        if body.node_id and (not node or node.source_id != source.id):
            raise HTTPException(404, "节点不存在")
        task = enqueue_check(db, source, node, settings, force=True)
        db.flush()
        return {"task_id": task.id, "status": "queued"}

    @app.get("/api/admin/suggestions")
    def suggestions(user=Depends(admin), db=transaction):
        rows = db.scalars(select(Suggestion).order_by(Suggestion.id.desc()).limit(200)).all()
        return {"items": [{"id": s.id, "work_id": s.work_id, "title": db.get(Work, s.work_id).title,
                           "changes": s.changes, "status": s.status, "reviewed_by": s.reviewed_by,
                           "reason": s.reason, "created_at": s.created_at} for s in rows]}

    @app.post("/api/admin/suggestions/{suggestion_id}/review")
    def moderate(suggestion_id: int, body: Review, user=Depends(admin), db=transaction):
        changed = db.execute(update(Suggestion).where(Suggestion.id == suggestion_id, Suggestion.status == "pending")
                             .values(status="accepted" if body.accept else "rejected", reviewed_by=user.id, reason=body.reason))
        if changed.rowcount != 1:
            raise HTTPException(409, "建议不存在或已经审核")
        suggestion = db.get(Suggestion, suggestion_id)
        work = db.get(Work, suggestion.work_id)
        before = serialize_work(db, work)
        if body.accept:
            apply_changes(db, work, validate_changes(suggestion.changes, work, db, public=True))
        audit(db, user, "suggestion.accept" if body.accept else "suggestion.reject", suggestion_id, before,
              {"changes": suggestion.changes, "reason": body.reason})
        return {"id": suggestion.id, "status": suggestion.status}

    @app.get("/api/admin/admins")
    def admins(user=Depends(admin), db=transaction):
        if not user.superuser:
            raise HTTPException(403, "仅超级管理员可管理账户")
        return {"items": [{"id": a.id, "username": a.username, "superuser": a.superuser, "active": a.active,
                           "created_at": a.created_at}
                          for a in db.scalars(select(Admin).order_by(Admin.id)).all()]}

    @app.post("/api/admin/admins", status_code=201)
    def new_admin(body: NewAdmin, user=Depends(admin), db=transaction):
        if not user.superuser:
            raise HTTPException(403, "仅超级管理员可创建账户")
        a = Admin(username=body.username, password_hash=password_hash(body.password), superuser=body.superuser)
        db.add(a)
        db.flush()
        audit(db, user, "admin.create", a.id, after={"username": a.username})
        return {"id": a.id, "username": a.username, "superuser": a.superuser}

    @app.patch("/api/admin/admins/{admin_id}")
    def patch_admin(admin_id: int, body: AdminPatch, user=Depends(admin), db=transaction):
        if not user.superuser:
            raise HTTPException(403, "仅超级管理员可管理账户")
        target = db.get(Admin, admin_id)
        if not target:
            raise HTTPException(404, "管理员不存在")
        changes = body.model_dump(exclude_unset=True)
        if target.id == user.id and changes.get("active") is False:
            raise HTTPException(409, "不能停用当前登录账户")
        if target.superuser and (changes.get("superuser") is False or changes.get("active") is False):
            remaining = db.scalar(select(func.count()).select_from(Admin).where(
                Admin.superuser.is_(True), Admin.active.is_(True), Admin.id != target.id)) or 0
            if remaining < 1:
                raise HTTPException(409, "至少保留一个启用的超级管理员")
        before = {"username": target.username, "active": target.active, "superuser": target.superuser}
        if "active" in changes and changes["active"] is not None:
            target.active = changes["active"]
        if "superuser" in changes and changes["superuser"] is not None:
            target.superuser = changes["superuser"]
        if changes.get("password"):
            target.password_hash = password_hash(changes["password"])
        if "active" in changes or changes.get("password"):
            db.execute(delete(SessionToken).where(SessionToken.admin_id == target.id))
        audit(db, user, "admin.update", target.id, before,
              {"username": target.username, "active": target.active, "superuser": target.superuser})
        return {"id": target.id, "username": target.username, "active": target.active, "superuser": target.superuser}

    @app.get("/api/admin/audits")
    def audits(user=Depends(admin), db=transaction):
        rows = db.scalars(select(Audit).order_by(Audit.id.desc()).limit(200)).all()
        return {"items": [{"id": a.id, "admin_id": a.admin_id, "action": a.action, "target": a.target,
                           "before": redact_audit(a.before), "after": redact_audit(a.after), "at": a.at} for a in rows]}

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/") or not dist.exists():
            raise HTTPException(404, "未找到页面，请先构建前端")
        target = (dist / path).resolve()
        if not target.is_relative_to(dist.resolve()):
            raise HTTPException(404)
        if target.is_file():
            return FileResponse(target)
        return FileResponse(dist / "index.html")

    return app
