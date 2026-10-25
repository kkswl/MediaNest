"""Bounded directory tests use synthetic rows only; no real 115 requests."""

import time

import pytest
from sqlalchemy import inspect, select

from app.adapters import ReadError
from app.db import Job, Node, Source, Task, Work
from app.worker import Worker


def ready(app):
    with app.state.database.session.begin() as db:
        for source in db.scalars(select(Source)):
            source.next_request = 0
        for task in db.scalars(select(Task).where(Task.status == "queued")):
            task.available_at = 0


@pytest.fixture
def scope(api, monkeypatch):
    app, owner, other, public, ids = api
    with app.state.database.session.begin() as db:
        source = db.get(Source, ids["source"])
        source.adapter = "live"
        node = db.scalar(select(Node).where(Node.source_id == source.id, Node.is_dir.is_(True),
                                            Node.name == "星海来信 (2024)").order_by(Node.id))
        node_id, remote_id, path = node.id, node.remote_id, node.path
    app.state.settings.live_enabled = True
    app.state.settings.live_root_only = True
    calls = []

    def page(source, directory, offset, limit):
        assert directory == remote_id
        with app.state.database.session() as db:
            job = db.scalar(select(Job).where(Job.scan_mode == "directory_preview").order_by(Job.id.desc()))
            assert job.scan_requests == len(calls) + 1  # reservation committed before IO
        calls.append((directory, offset, limit))
        return [{"id": f"synthetic-{i}", "name": f"模拟子目录{i}", "is_dir": True}
                for i in range(offset, min(offset + limit, 5))], 5

    def forbidden(*args, **kwargs):
        pytest.fail("bounded live preview must not read NFO or call TMDB")

    monkeypatch.setattr(app.state.readers, "page", page)
    monkeypatch.setattr(app.state.readers, "nfo", forbidden)
    monkeypatch.setattr(app.state.worker.tmdb, "match", forbidden)
    yield app, owner, other, public, ids, node_id, remote_id, path, calls


def launch(scope):
    _app, owner, _other, _public, ids, node_id, *_ = scope
    response = owner.post(f"/api/admin/sources/{ids['source']}/directories/{node_id}/scan", json={})
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


def test_directory_preview_owner_scope_two_pages_and_resume(scope):
    app, owner, other, public, ids, node_id, remote_id, path, calls = scope
    endpoint = f"/api/admin/sources/{ids['source']}/directories/{node_id}/scan"
    assert public.post(endpoint, json={}).status_code == 401
    assert other.post(endpoint, json={}).status_code == 404
    jid = launch(scope)
    assert owner.post(endpoint, json={}).json()["job_id"] == jid
    assert owner.post(f"/api/admin/sources/{ids['source']}/scan", json={}).status_code == 400
    assert app.state.worker.tick()
    assert owner.post(f"/api/admin/jobs/{jid}/pause", json={}).status_code == 200
    ready(app)
    assert not app.state.worker.tick()
    assert owner.post(f"/api/admin/jobs/{jid}/resume", json={}).status_code == 200
    restarted = Worker(app.state.database, app.state.settings, app.state.readers)
    assert restarted.tick()
    ready(app)
    assert not restarted.tick()
    assert calls == [(remote_id, 0, 2), (remote_id, 2, 2)]
    job = next(j for j in owner.get("/api/admin/jobs").json()["items"] if j["id"] == jid)
    assert job["scan_mode"] == "directory_preview" and job["scope_path"] == path
    assert job["scan_requests"] == job["pages_read"] == job["request_limit"] == 2
    assert job["nodes_read"] == 4 and job["truncated"] and not job["recursive"]
    assert job["status"] == "complete"  # completed bounded range, NOT a complete source
    with app.state.database.session() as db:
        tasks = db.scalars(select(Task).where(Task.job_id == jid)).all()
        assert len(tasks) == 1 and tasks[0].target == remote_id
        children = db.scalars(select(Node).where(Node.remote_id.like("synthetic-%"))).all()
        assert len(children) == 4
        assert all(n.parent_remote_id == remote_id and n.path.startswith(path + "/") for n in children)
    # Cache browsing and search must not create any real jobs or health reads.
    for _ in range(2):
        assert owner.get(f"/api/admin/sources/{ids['source']}/nodes", params={"parent": remote_id}).status_code == 200
        assert public.get("/api/catalog", params={"q": "星海"}).status_code == 200
    ready(app)
    assert not restarted.tick()
    assert len(calls) == 2


@pytest.mark.parametrize("invalid", ["file", "wrong_source", "bad_path", "missing_parent", "cycle"])
def test_directory_selection_rejects_invalid_nodes(scope, invalid):
    app, owner, _other, _public, ids, node_id, *_ = scope
    with app.state.database.session.begin() as db:
        node = db.get(Node, node_id)
        if invalid == "file":
            node.is_dir = False
        elif invalid == "wrong_source":
            source = Source(owner_id=ids["other"], code="demob", url="https://115.com/s/demob", adapter="mock")
            db.add(source)
            db.flush()
            node.source_id = source.id
        elif invalid == "bad_path":
            node.path = "../forged"
        elif invalid == "missing_parent":
            node.parent_remote_id = "not-cached"
        else:
            node.parent_remote_id = node.remote_id
    result = owner.post(f"/api/admin/sources/{ids['source']}/directories/{node_id}/scan", json={})
    assert result.status_code == 400, result.text
    assert scope[-1] == []


@pytest.mark.parametrize("field", ["target", "path", "scope_path", "scope_owner"])
def test_forged_task_or_changed_scope_never_calls_reader(scope, field):
    app = scope[0]
    jid = launch(scope)
    with app.state.database.session.begin() as db:
        task = db.scalar(select(Task).where(Task.job_id == jid))
        job = db.get(Job, jid)
        if field == "target":
            task.target = "forged"
        elif field == "path":
            task.payload = dict(task.payload, path="forged")
        elif field == "scope_path":
            job.scope_path = "forged"
        else:
            job.owner_id = scope[4]["other"]
    assert not app.state.worker.tick()
    assert scope[-1] == []
    with app.state.database.session() as db:
        assert db.get(Job, jid).scan_requests == 0


def test_crash_claim_reservation_is_not_reset(scope):
    app, owner, *_ = scope
    jid = launch(scope)
    tid, _lease = app.state.worker.claim()
    with app.state.database.session.begin() as db:
        assert db.get(Job, jid).scan_requests == 1
        db.get(Task, tid).lease_until = time.time() - 1
        db.get(Source, scope[4]["source"]).next_request = 0
    # One reservation was lost to a crash; only one more IO is permitted.
    def page(*args):
        scope[-1].append(args)
        return [], 0
    app.state.readers.page = page
    restarted = Worker(app.state.database, app.state.settings, app.state.readers)
    assert restarted.tick()
    ready(app)
    assert not restarted.tick()
    with app.state.database.session() as db:
        assert db.get(Job, jid).scan_requests == 2
        assert db.get(Job, jid).pages_read == 1
    assert len(scope[-1]) == 1
    assert owner.post(f"/api/admin/jobs/{jid}/retry", json={}).status_code == 409


@pytest.mark.parametrize("kind", ["timeout", "rate_limited", "auth", "incomplete"])
def test_directory_failures_retry_preserves_budget_and_health(scope, kind):
    app, owner, *_ = scope
    jid = launch(scope)
    calls = []
    def fail(*args):
        calls.append(args)
        raise ReadError(kind, "secret-not-to-log")
    app.state.readers.page = fail
    assert app.state.worker.tick()
    ready(app)
    app.state.worker.tick()
    ready(app)
    app.state.worker.tick()
    with app.state.database.session() as db:
        job = db.get(Job, jid)
        assert job.scan_requests <= 2 and job.pages_read == job.nodes_read == 0
        source = db.get(Source, scope[4]["source"])
        assert source.failures == 0 and source.health != "missing"
        task = db.scalar(select(Task).where(Task.job_id == jid))
        assert "secret-not-to-log" not in task.error
        used = job.scan_requests
    assert owner.post(f"/api/admin/jobs/{jid}/retry", json={}).status_code == 200
    ready(app)
    app.state.worker.tick()
    ready(app)
    app.state.worker.tick()
    with app.state.database.session() as db:
        assert db.get(Job, jid).scan_requests >= used
        assert db.get(Job, jid).scan_requests <= 2
    assert len(calls) <= 2


def test_mock_directory_identification_closure(api):
    app, owner, _other, _public, ids = api
    with app.state.database.session.begin() as db:
        node = db.scalar(select(Node).where(Node.name == "星海来信-poster.jpg"))
        directory = db.scalar(select(Node).where(Node.source_id == ids["source"], Node.remote_id == node.parent_remote_id))
        node_id = directory.id
    app.state.settings.page_size = 50
    response = owner.post(f"/api/admin/sources/{ids['source']}/directories/{node_id}/scan", json={})
    assert response.status_code == 201
    jid = response.json()["job_id"]
    app.state.worker.drain()
    with app.state.database.session() as db:
        job = db.get(Job, jid)
        assert job.status == "complete" and job.scan_requests == 1
        assert db.scalar(select(Work).where(Work.title == "星海来信")) is not None
        assert set(db.scalars(select(Task.kind).where(Task.job_id == jid))) == {"scan", "identify", "identify_media"}
        assert "scope_path" in {c["name"] for c in inspect(db.get_bind()).get_columns("jobs")}


@pytest.mark.parametrize("failure", [False, True])
def test_directory_stale_worker_cannot_commit_success_or_error(scope, failure):
    app = scope[0]
    jid = launch(scope)
    def superseded(*args):
        with app.state.database.session.begin() as db:
            task = db.scalar(select(Task).where(Task.job_id == jid))
            task.lease_token = "new-worker-token"
            task.error = "new-worker-result"
        if failure:
            raise ReadError("timeout", "stale-error")
        return [{"id": "stale-node", "name": "不得落库.mkv", "is_dir": False}], 1
    app.state.readers.page = superseded
    assert app.state.worker.tick()
    with app.state.database.session() as db:
        task = db.scalar(select(Task).where(Task.job_id == jid))
        assert task.lease_token == "new-worker-token" and task.error == "new-worker-result"
        assert not db.scalar(select(Node.id).where(Node.remote_id == "stale-node"))
        assert db.get(Job, jid).pages_read == 0
        assert db.get(Job, jid).scan_requests == 1


@pytest.mark.parametrize("failure", ["changing_total", "duplicate_page", "empty_page", "ancestor_page"])
def test_incomplete_second_page_does_not_hide_or_claim_complete(scope, failure):
    app = scope[0]
    jid = launch(scope)
    assert app.state.worker.tick()
    ready(app)
    def incomplete(source, directory, offset, limit):
        if failure == "changing_total":
            return [{"id": "new", "name": "新目录", "is_dir": True}], 6
        if failure == "duplicate_page":
            return [{"id": "synthetic-0", "name": "重复目录", "is_dir": True}], 5
        if failure == "ancestor_page":
            with app.state.database.session() as db:
                ancestor = db.scalar(select(Node).where(Node.source_id == scope[4]["source"],
                                                        Node.name == "林舟作品合集"))
                ancestor_id = ancestor.remote_id
            return [{"id": ancestor_id, "name": "伪造祖先目录", "is_dir": True}], 5
        return [], 5
    app.state.readers.page = incomplete
    assert app.state.worker.tick()
    with app.state.database.session() as db:
        job = db.get(Job, jid)
        assert job.status == "partial" and job.scan_requests == 2 and job.pages_read == 1
        task = db.scalar(select(Task).where(Task.job_id == jid))
        assert task.status == "failed" and task.error.startswith("incomplete:")
        assert db.get(Source, scope[4]["source"]).failures == 0


def test_v3_migration_preserves_existing_scopes_and_budget(tmp_path):
    from app.db import Database
    database = Database("sqlite:///" + str(tmp_path / "legacy.db"))
    with database.engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE jobs (id INTEGER PRIMARY KEY, source_id INTEGER, owner_id INTEGER, status TEXT)")
        connection.exec_driver_sql("INSERT INTO jobs VALUES (1, 1, 1, 'paused')")
    database.init()
    database.init()
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT status, scan_requests, scope_path FROM jobs").one() == ("paused", 0, "")
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM schema_migrations WHERE version=3").scalar() == 1
    database.engine.dispose()


def test_mock_scoped_index_creates_and_merges_work_from_empty_catalog(environment):
    from app.db import Variant
    from app.fixtures import directory_fixture
    from app.scan_scope import start_directory_scan
    database, settings, _readers, worker, ids = environment
    settings.page_size = 50
    tree, _contents = directory_fixture("demoa")
    with database.session.begin() as db:
        assert db.scalar(select(Work)) is None
        db.get(Job, ids["job"]).status = "cancelled"
        db.scalar(select(Task)).status = "cancelled"
        path = ""
        parent = "0"
        for _ in range(3):
            item = tree[parent][0]
            path = "/".join(filter(None, (path, item["name"])))
            node = Node(source_id=ids["source"], remote_id=item["id"], parent_remote_id=parent,
                        name=item["name"], path=path, is_dir=True)
            db.add(node)
            parent = item["id"]
        db.flush()
        job = start_directory_scan(db, db.get(Source, ids["source"]), node.id)
        jid = job.id
    worker.drain()
    with database.session() as db:
        works = db.scalars(select(Work)).all()
        assert len(works) == 1 and works[0].title == "星海来信" and works[0].status == "confirmed"
        variants = db.scalars(select(Variant).where(Variant.work_id == works[0].id)).all()
        assert len(variants) == 2 and {v.attributes["format"] for v in variants} == {"MKV", "ISO"}
        assert db.get(Job, jid).scan_requests == db.get(Job, jid).pages_read == 1
