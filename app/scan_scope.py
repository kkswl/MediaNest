"""Immutable, owner-bound directory scope for explicitly requested previews."""

from sqlalchemy import select

from .adapters import ReadError
from .db import Job, Node, Task


def directory_scope(db, source, node_id):
    node = db.get(Node, node_id)
    if not node or node.source_id != source.id or not node.is_dir or node.remote_id == "0":
        raise ValueError("请选择此来源中已记录的目录节点")
    chain, seen, cursor = [], set(), node
    while cursor:
        if cursor.remote_id in seen or len(chain) >= 100 or not cursor.is_dir:
            raise ValueError("目录层级不完整或存在循环")
        if (not cursor.name or cursor.name in (".", "..") or "/" in cursor.name
                or "\\" in cursor.name or any(ord(c) < 32 for c in cursor.name)):
            raise ValueError("目录名称不符合安全路径规则")
        seen.add(cursor.remote_id)
        chain.append(cursor)
        if cursor.parent_remote_id == "0":
            break
        cursor = db.scalar(select(Node).where(Node.source_id == source.id,
                                             Node.remote_id == cursor.parent_remote_id))
        if cursor is None:
            raise ValueError("父目录尚未完整记录，请先建立目录索引")
    path = ""
    for ancestor in reversed(chain):
        path = "/".join(filter(None, (path, ancestor.name)))
        if ancestor.path != path:
            raise ValueError("目录路径与节点层级不一致，请重新确认")
    return node


def start_directory_scan(db, source, node_id):
    node = directory_scope(db, source, node_id)
    active = db.scalar(select(Job).where(Job.source_id == source.id,
                                        Job.status.in_(["queued", "running", "paused"])))
    if active:
        if active.scan_mode == "directory_preview" and active.scope_node_id == node.id:
            return active
        raise ValueError("此来源已有其他范围任务，请先完成或取消")
    job = Job(source_id=source.id, owner_id=source.owner_id, scan_mode="directory_preview",
              scope_node_id=node.id, scope_remote_id=node.remote_id, scope_path=node.path)
    db.add(job)
    db.flush()
    db.add(Task(job_id=job.id, source_id=source.id, kind="scan", target=node.remote_id,
                dedupe_key=f"job:{job.id}:scan:{node.remote_id}", payload={"offset": 0, "path": node.path}))
    return job


def validate_directory_task(db, source, job, task):
    try:
        node = directory_scope(db, source, job.scope_node_id)
        if (job.owner_id != source.owner_id or job.source_id != source.id
                or task.source_id != source.id or node.remote_id != job.scope_remote_id
                or node.path != job.scope_path):
            raise ValueError("目录授权与当前节点不一致")
        if task.kind == "scan":
            if (task.target != node.remote_id or task.payload.get("path") != node.path
                    or task.dedupe_key != f"job:{job.id}:scan:{node.remote_id}"):
                raise ValueError("任务目标超出指定目录")
        elif task.kind in ("identify", "identify_media"):
            scan = db.scalar(select(Task).where(Task.job_id == job.id, Task.kind == "scan"))
            if not scan or scan.status != "done" or job.pages_read < 1:
                raise ValueError("目录分页尚未成功完成")
            if task.kind == "identify" and task.target != node.remote_id:
                raise ValueError("识别超出指定目录")
            if task.kind == "identify_media":
                media = db.get(Node, int(task.target))
                if (not media or media.source_id != source.id or media.parent_remote_id != node.remote_id
                        or media.remote_id not in scan.payload.get("seen", [])
                        or task.payload.get("directory") != node.remote_id):
                    raise ValueError("识别节点超出指定目录实际返回范围")
        else:
            raise ValueError("范围索引禁止此类读取")
    except (ValueError, TypeError) as exc:
        raise ReadError("scope_limit", "指定目录授权校验失败") from exc
