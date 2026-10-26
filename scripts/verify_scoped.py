"""Opt-in single-source existing-directory regression; secrets only via process env.

Run against an explicitly backed-up local DB. No daemon, recursion, Cookie,
NFO, images, media or TMDB I/O. The durable run ledger fails closed on reuse
after an error; changing a run ID requires NEW human authorization.
"""

import json
import os
import re
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters import ReadError
from app.config import Settings, local_file_lock
from app.db import Job, Node, Source, Task
from app.main import create_app
from app.worker import Worker


class Budget:
    def __init__(self, path, source_id, node_id):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with local_file_lock(self.path.with_suffix(".lock")):
            if self.path.exists():
                saved = self.read()
                if saved["source_id"] != source_id or saved["node_id"] != node_id:
                    raise ValueError("run scope mismatch")
            else:
                self.write({"source_id": source_id, "node_id": node_id, "directory": 0, "health": 0,
                            "stopped": False, "finished": False})

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, state):
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(state, handle)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(self.path)

    def update(self, **changes):
        with local_file_lock(self.path.with_suffix(".lock")):
            state = self.read()
            state.update(changes)
            self.write(state)

    def reserve(self, phase):
        with local_file_lock(self.path.with_suffix(".lock")):
            state = self.read()
            if (phase not in ("directory", "health") or state["stopped"] or state["finished"]
                    or state[phase] >= (2 if phase == "directory" else 1)
                    or state["directory"] + state["health"] >= 5):
                raise ReadError("scope_limit", "持久化验证预算已耗尽或停止")
            state[phase] += 1
            self.write(state)  # commit before I/O, even if the process dies next


def run():
    if os.getenv("CONFIRM_SCOPED_READ") != "yes-I-authorize":
        raise ValueError("explicit authorization required")
    settings = Settings()
    settings.live_enabled, settings.live_root_only = True, True
    settings.interval = max(2, settings.interval)
    settings.tmdb_enabled, settings.tmdb_token = False, ""
    run_id = os.environ["VERIFY_RUN_ID"]
    if not re.fullmatch(r"[A-Za-z0-9-]{1,80}", run_id):
        raise ValueError("invalid run ID")
    sid, nid = int(os.environ["VERIFY_SOURCE_ID"]), int(os.environ["VERIFY_NODE_ID"])
    app = create_app(settings)
    database, readers = app.state.database, app.state.readers
    budget = Budget(Path(settings.state_dir) / "verification" / (run_id + ".json"), sid, nid)
    stage = "directory"
    with database.session() as db:
        source, node = db.get(Source, sid), db.get(Node, nid)
        if (not source or not node or source.adapter != "live" or source.credential
                or source.code != os.environ["VERIFY_SHARE_CODE"]
                or node.source_id != sid or not node.is_dir):
            raise ValueError("source/directory mismatch or requires private credentials")
        code, remote = source.code, node.remote_id
    saved = budget.read()
    if saved["finished"] or saved["stopped"]:
        settings.live_enabled = False
        database.engine.dispose()
        return {"status": "already_finished_or_stopped", "directory_requests": saved["directory"],
                "health_requests": saved["health"]}
    actual = readers.live.public_snap

    def bounded(payload):
        if payload.get("share_code") != code or str(payload.get("cid")) != (remote if stage == "directory" else "0"):
            raise ReadError("scope_limit", "source or directory outside authorization")
        budget.reserve(stage)
        return actual(payload)

    def forbidden(*args, **kwargs):
        raise ReadError("scope_limit", "verification forbids metadata I/O")

    readers.live.public_snap = bounded
    readers.nfo = forbidden

    def checked(response):
        if response.status_code >= 300:
            raise RuntimeError("local API failed")
        return response.json()

    def drain(worker, job_id=None, task_id=None):
        worker.tmdb.match = forbidden
        # Two 50-node pages may require >200s of serial local identification;
        # this extends only local processing time, never the network budget.
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            with database.session() as db:
                query = select(Task).where(Task.status.in_(("queued", "running")))
                query = query.where(Task.job_id == job_id) if job_id else query.where(Task.id == task_id)
                task = db.scalar(query.order_by(Task.available_at, Task.id))
                if not task:
                    return
                wait = max(0, task.available_at - time.time(), db.get(Source, sid).next_request - time.time())
            if wait:
                time.sleep(min(wait, 2))
                continue
            if not worker.tick():
                return
            with database.session() as db:
                current = db.get(Task, task.id)
                if current.error:
                    budget.update(stopped=True)
                    return  # never auto-retry a failing endpoint during this run
        budget.update(stopped=True)
        raise TimeoutError("bounded local workflow deadline")

    try:
        with TestClient(app) as client:
            checked(client.post("/api/login", json={"username": os.environ["VERIFY_ADMIN"],
                                                   "password": os.environ["VERIFY_PASSWORD"]}))
            jid = saved.get("job_id")
            if not jid:
                job = checked(client.post(f"/api/admin/sources/{sid}/directories/{nid}/scan", json={}))
                jid = job["job_id"]
                budget.update(job_id=jid)
            drain(Worker(database, settings, readers, job_id=jid), job_id=jid)
            if not budget.read()["stopped"]:
                stage = "health"
                tid = saved.get("health_task_id")
                if not tid:
                    tid = checked(client.post("/api/admin/recheck", json={"source_id": sid}))["task_id"]
                    budget.update(health_task_id=tid)
                drain(Worker(database, settings, readers, task_id=tid), task_id=tid)
            if budget.read()["stopped"]:
                with database.session() as db:
                    job = db.get(Job, jid)
                    if job.status in ("queued", "running"):
                        checked(client.post(f"/api/admin/jobs/{jid}/pause", json={}))
            else:
                budget.update(finished=True)
            checked(client.post("/api/logout", json={}))
        with database.session() as db:
            job = db.get(Job, jid)
            state = budget.read()
            return {"status": "stopped" if state["stopped"] else "finished", "job_id": jid,
                    "job_status": job.status, "pages": job.pages_read, "nodes": job.nodes_read,
                    "directory_requests": state["directory"], "health_requests": state["health"],
                    "serial": True, "nfo_requests": 0, "tmdb_requests": 0, "remote_writes": 0}
    except Exception:
        budget.update(stopped=True)
        raise
    finally:
        settings.live_enabled = False
        database.engine.dispose()


if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 -- CLI boundary must not print secrets in transport errors
        print(json.dumps({"status": "failed", "exception_type": type(exc).__name__}))
        raise SystemExit(1) from None
