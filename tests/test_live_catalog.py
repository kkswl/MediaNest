"""Offline real-adapter/API pipeline; no real services or media content."""

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.adapters import ReadError
from app.config import Settings
from app.db import Admin, HealthEvent, Job, Node, Source, Task, Variant, Work
from app.main import create_app
from app.security import password_hash, share_link


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    settings = Settings(database_url="sqlite:///" + str(tmp_path / "index.db"),
                        state_dir=str(tmp_path / "state"), secret="s" * 48, live_enabled=True,
                        tmdb_enabled=True, tmdb_token="synthetic-never-request", page_size=50,
                        public_image_hosts=("cdn.example.org",), interval=0.1)
    app = create_app(settings)
    with app.state.database.session.begin() as db:
        db.add(Admin(username="test-admin", password_hash=password_hash("synthetic-password-2026")))
    calls = []

    def snap(payload):
        calls.append(dict(payload))
        if payload["cid"] == "0":
            values = [{"cid": "100", "pid": "0", "n": "Synthetic Film (2024)"}]
        else:
            assert payload["cid"] == "100"
            values = [
                {"fid": "201", "cid": "100", "n": "Synthetic.Film.2024.1080p.mkv"},
                {"fid": "202", "cid": "100", "n": "Synthetic.Film.2024.2160p.iso"},
                {"fid": "203", "cid": "100", "n": "Synthetic.Series.S01E01.1080p.mkv"},
                {"fid": "204", "cid": "100", "n": "Synthetic.Series.S01E02.2160p.mkv"},
                {"fid": "205", "cid": "100", "n": "movie.nfo"},
                {"fid": "206", "cid": "100", "n": "Synthetic Film-poster.jpg",
                 "thumb_url": "https://cdn.example.org/film.jpg"},
                {"cid": "207", "pid": "100", "n": "BDMV"},
                {"cid": "208", "pid": "100", "n": "电影合集"},
            ]
        offset = payload["offset"]
        return {"state": True, "data": {"list": values[offset:offset + payload["limit"]], "count": len(values)}}

    def forbidden(*args, **kwargs):
        pytest.fail("bounded identification must NEVER read NFO/TMDB/content")

    monkeypatch.setattr(app.state.readers.live, "public_snap", snap)
    monkeypatch.setattr(app.state.readers, "nfo", forbidden)
    monkeypatch.setattr(app.state.worker.tmdb, "match", forbidden)
    with TestClient(app) as client:
        assert client.post("/api/login", json={"username": "test-admin", "password": "synthetic-password-2026"}).status_code == 200
        result = client.post("/api/admin/import", json={"adapter": "live", "items": [
            {"url": "https://115cdn.com/s/syntheticpipeline?password=aaaa"}]}).json()["items"][0]
        yield app, client, result, calls
    app.state.database.engine.dispose()


def run_queue(app):
    for _ in range(30):
        with app.state.database.session.begin() as db:
            for s in db.scalars(select(Source)):
                s.next_request = 0
            for t in db.scalars(select(Task).where(Task.status == "queued")):
                t.available_at = 0
        if not app.state.worker.tick():
            return
    pytest.fail("queue did not finish")


def launch_directory(app, client, result):
    run_queue(app)
    with app.state.database.session() as db:
        node = db.scalar(select(Node).where(Node.source_id == result["id"], Node.remote_id == "100"))
        node_id = node.id
    response = client.post(f"/api/admin/sources/{result['id']}/directories/{node_id}/scan", json={})
    assert response.status_code == 201, response.text
    return response.json()["job_id"]


def test_live_scoped_index_review_and_publication(pipeline):
    app, client, result, calls = pipeline
    jid = launch_directory(app, client, result)
    # A previously cached but NOT returned node must not enter this job.
    with app.state.database.session.begin() as db:
        db.add(Node(source_id=result["id"], remote_id="999", parent_remote_id="100",
                    name="Not.Returned.2020.mkv", path="Synthetic Film (2024)/Not.Returned.2020.mkv", is_dir=False))
    run_queue(app)
    assert len(calls) == 2 and [p["cid"] for p in calls] == ["0", "100"]
    assert client.get("/api/stats").json()["works"] == 0
    assert client.get("/api/stats").json()["variants"] == 0
    review = client.get("/api/admin/review").json()["items"]
    assert len(review) == 2, review
    with app.state.database.session() as db:
        job = db.get(Job, jid)
        assert job.status == "complete" and job.scan_requests == job.pages_read == 1
        assert set(db.scalars(select(Task.kind).where(Task.job_id == jid))) == {"scan", "identify", "identify_media"}
        works = db.scalars(select(Work)).all()
        assert all(w.status == "review" for w in works)
        assert not any(w.title == "Not Returned" for w in works)
        movie = next(w for w in works if w.category == "movie")
        series = next(w for w in works if w.category == "tv")
        movie_id = movie.id
        versions = db.scalars(select(Variant).where(Variant.work_id == movie.id)).all()
        assert {v.attributes["format"] for v in versions} == {"MKV", "ISO", "BDMV"}
        episodes = db.scalars(select(Variant).where(Variant.work_id == series.id)).all()
        assert {v.season for v in episodes} == {1}
        assert sorted(v.episodes for v in episodes) == [[1], [2]]
        assert movie.info["poster"] == "https://cdn.example.org/film.jpg"
    assert client.get(f"/api/works/{movie_id}").status_code == 404
    approved = client.patch(f"/api/admin/works/{movie_id}", json={"status": "confirmed"})
    assert approved.status_code == 200, approved.text
    assert client.get("/api/stats").json()["works"] == 1
    assert client.get("/api/stats").json()["variants"] == 3
    detail = client.get(f"/api/works/{movie_id}").json()
    assert all(v["share_url"] == "https://115cdn.com/s/syntheticpipeline?password=aaaa" for v in detail["variants"])
    assert all(v["web_page_status"] == "not_verified" and not v["is_demo"] for v in detail["variants"])
    assert len(calls) == 2  # API reads never trigger network
    # An offline rescan must retain previously observed NFO evidence even though
    # this bounded run is forbidden from re-reading the sidecar.
    from app.metadata import identify_directory
    from app.posters import observe_poster
    with app.state.database.session.begin() as db:
        work = db.get(Work, movie_id)
        variant = db.scalar(select(Variant).where(Variant.work_id == movie_id))
        source = db.get(Source, variant.source_id)
        observe_poster(work, "nfo", "https://cdn.example.org/nfo.jpg", ("cdn.example.org",), source.id, variant.node_id)
        identify_directory(db, source, "100", app.state.readers, app.state.worker.tmdb,
                           media_node_id=variant.node_id, local_only=True)
        assert work.info["poster"] == "https://cdn.example.org/nfo.jpg"
        assert work.status == "confirmed"


@pytest.mark.parametrize("kind", ["missing", "timeout", "auth", "rate_limited", "incomplete"])
def test_scan_error_persists_targeted_health(pipeline, kind):
    app, client, result, _calls = pipeline
    jid = launch_directory(app, client, result)
    def fail(*args):
        raise ReadError(kind, "never log this")
    app.state.readers.page = fail
    assert app.state.worker.tick()
    with app.state.database.session() as db:
        source = db.get(Source, result["id"])
        node = db.get(Node, db.get(Job, jid).scope_node_id)
        assert source.health == "healthy" and source.failures == 0
        assert node.health == ("pending" if kind == "missing" else "uncertain")
        assert node.failures == (1 if kind == "missing" else 0)
        event = db.scalar(select(HealthEvent).where(HealthEvent.node_id == node.id).order_by(HealthEvent.id.desc()))
        assert event.result == ("auth_failed" if kind == "auth" else kind)


def test_stale_identification_cannot_commit(pipeline, monkeypatch):
    app, client, result, _calls = pipeline
    jid = launch_directory(app, client, result)
    # Scan and discover only, then supersede the identify_media lease.
    for _ in range(2):
        with app.state.database.session.begin() as db:
            db.get(Source, result["id"]).next_request = 0
        assert app.state.worker.tick()
    import app.worker as module
    original = module.identify_directory
    def superseded(*args, **kwargs):
        with app.state.database.session.begin() as db:
            task = db.scalar(select(Task).where(Task.job_id == jid, Task.kind == "identify_media", Task.status == "running"))
            task.lease_token = "replacement-worker"
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "identify_directory", superseded)
    with app.state.database.session.begin() as db:
        db.get(Source, result["id"]).next_request = 0
        for t in db.scalars(select(Task).where(Task.kind == "identify")):
            t.available_at = time.time() + 3600
    assert app.state.worker.tick()
    with app.state.database.session() as db:
        assert db.scalar(select(Work.id)) is None
        assert db.scalar(select(Task).where(Task.lease_token == "replacement-worker")) is not None


def test_share_url_consistency_and_demo_suppression():
    source = SimpleNamespace(adapter="live", code="synthetic", access_code="bbbb",
                             url="https://115.com/s/synthetic?password=old#fragment")
    assert share_link(source) == "https://115.com/s/synthetic?password=bbbb"
    assert source.url.endswith("old#fragment")  # original evidence is not overwritten
    source.adapter = "mock"
    assert share_link(source) == ""
    source.adapter, source.url = "live", "https://evil.example/s/synthetic"
    assert share_link(source) == ""


def test_filtered_worker_does_not_recover_other_job_leases(pipeline):
    from app.worker import Worker
    app, client, result, _calls = pipeline
    jid = launch_directory(app, client, result)
    with app.state.database.session.begin() as db:
        unrelated = db.scalar(select(Task).where(Task.job_id == result["job_id"]))
        unrelated.status = "running"
        unrelated.lease_token = "unrelated-worker"
        unrelated.lease_until = time.time() - 1
        tid = unrelated.id
    worker = Worker(app.state.database, app.state.settings, app.state.readers, job_id=jid)
    assert worker.tick()
    with app.state.database.session() as db:
        assert db.get(Task, tid).status == "running"
        assert db.get(Task, tid).lease_token == "unrelated-worker"


@pytest.mark.parametrize("restricted", [False, True])
def test_scoped_runner_uses_api_and_never_replays_finished_run(pipeline, monkeypatch, restricted):
    from app.adapters import P115Reader
    from scripts import verify_scoped
    app, _client, result, calls = pipeline
    run_queue(app)
    with app.state.database.session() as db:
        nid = db.scalar(select(Node.id).where(Node.remote_id == "100"))
    snap = app.state.readers.live.public_snap
    def respond(self, payload):
        if restricted:
            calls.append(dict(payload))
            return {"state": False, "error": "请求频繁"}
        return snap(payload)
    monkeypatch.setattr(P115Reader, "public_snap", respond)
    monkeypatch.setattr(verify_scoped, "Settings", lambda: app.state.settings)
    for key, value in {"CONFIRM_SCOPED_READ": "yes-I-authorize", "VERIFY_RUN_ID": "synthetic-run",
                       "VERIFY_SOURCE_ID": str(result["id"]), "VERIFY_NODE_ID": str(nid),
                       "VERIFY_SHARE_CODE": "syntheticpipeline", "VERIFY_ADMIN": "test-admin",
                       "VERIFY_PASSWORD": "synthetic-password-2026"}.items():
        monkeypatch.setenv(key, value)
    report = verify_scoped.run()
    assert report["directory_requests"] == 1
    assert report["health_requests"] == (0 if restricted else 1)
    assert report["status"] == ("stopped" if restricted else "finished")
    assert not app.state.settings.live_enabled
    before = len(calls)
    repeat = verify_scoped.run()
    assert repeat["status"] == "already_finished_or_stopped"
    assert len(calls) == before
    assert not app.state.settings.live_enabled
