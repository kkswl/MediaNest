import time

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import HealthEvent, Node, Task


def record_health(db, source, node, result, reason, settings):
    # Keep legacy adapter kind `auth` accepted while exposing an explicit event category.
    result = "auth_failed" if result == "auth" else result
    target = node if node is not None else source
    now = time.time()
    target.checked_at = now
    if result == "healthy":
        target.failures = 0
        target.health = "healthy"
    elif result == "missing":
        target.failures += 1
        target.health = "missing" if target.failures >= settings.failure_threshold else "pending"
    else:
        # Uncertainty never clears an already confirmed missing state, nor increments failures.
        if target.health not in ("missing", "pending"):
            target.health = "uncertain"
    db.add(HealthEvent(source_id=source.id, node_id=node.id if node else None,
                       result=result, state=target.health, reason=reason[:1000], at=now))


def effective_health(db, source, node):
    if not source.enabled or source.health == "missing":
        return "missing"
    state = source.health
    visited = set()
    cursor = node
    while cursor and cursor.id not in visited:
        visited.add(cursor.id)
        if cursor.health == "missing":
            return "missing"
        if cursor.health == "pending":
            state = "pending"
        elif cursor.health == "uncertain" and state != "pending":
            state = "uncertain"
        cursor = db.scalar(select(Node).where(Node.source_id == source.id,
                                               Node.remote_id == cursor.parent_remote_id))
    return state if state not in ("unchecked", "") else "healthy"


def enqueue_check(db, source, node=None, settings=None, force=False):
    target = node if node is not None else source
    if not force and settings and target.checked_at and time.time() - target.checked_at < settings.health_ttl:
        return None
    dedupe = f"health:{source.id}:{node.id if node else 'root'}"
    existing = db.scalar(select(Task).where(Task.dedupe_key == dedupe))
    if existing:
        return existing
    dialect = db.get_bind().dialect.name
    insert = sqlite_insert if dialect == "sqlite" else pg_insert if dialect == "postgresql" else None
    if insert is None:
        raise RuntimeError("任务去重仅支持 SQLite / PostgreSQL")
    # Search and manual rechecks may enqueue the same target simultaneously.
    # The unique key, not a preceding SELECT, is the concurrency authority.
    db.execute(insert(Task).values(source_id=source.id, kind="health",
               target=str(node.id) if node else "root", dedupe_key=dedupe,
               payload={"offset": 0, "found": False})
               .on_conflict_do_nothing(index_elements=[Task.dedupe_key]))
    return db.scalar(select(Task).where(Task.dedupe_key == dedupe))
