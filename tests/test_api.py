import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Admin, Audit, Node, Source, Suggestion, Task, Work
from app.health import record_health
from app.main import create_app
from app.metadata import identify_directory
from app.security import password_hash


@pytest.fixture
def api(environment):
    database, settings, _readers, _worker, ids = environment
    with database.session.begin() as db:
        db.get(Admin, ids["admin"]).superuser = True
        other = Admin(username="other-admin", password_hash=password_hash("other-password-2026"))
        db.add(other)
        db.flush()
        ids["other"] = other.id
    app = create_app(settings)
    app.state.worker.drain()
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as public:
        assert owner.post("/api/login", json={"username": "test-admin", "password": "test-password-2026"}).status_code == 200
        assert other.post("/api/login", json={"username": "other-admin", "password": "other-password-2026"}).status_code == 200
        yield app, owner, other, public, ids
    app.state.database.engine.dispose()


def test_public_catalog_paths_and_metadata_filters(api):
    _app, _owner, _other, public, _ids = api
    catalog = public.get("/api/catalog", params={"q": "星海", "format": "ISO"})
    assert catalog.status_code == 200, catalog.text
    items = catalog.json()["items"]
    assert len(items) == 1 and items[0]["title"] == "星海来信"
    detail = public.get(f"/api/works/{items[0]['id']}").json()
    assert len(detail["variants"]) == 3
    assert all(v["path"].startswith("林舟作品合集/星海系列合集/") for v in detail["variants"])
    assert all(v["share_url"].startswith("https://115.com/s/demoa") for v in detail["variants"])
    assert all(v["access_code"] == "aaaa" for v in detail["variants"])
    people = public.get("/api/people").json()["items"]
    collections = public.get("/api/collections").json()["items"]
    person = next(x for x in people if x["name"] == "林舟")
    collection = next(x for x in collections if x["name"] == "星海系列")
    assert public.get("/api/catalog", params={"person": person["id"]}).json()["total"] > 0
    assert public.get("/api/catalog", params={"collection": collection["id"]}).json()["total"] == 1
    assert public.get("/api/catalog", params={"q": "不存在的虚构作品"}).json()["total"] == 0
    assert public.get("/api/catalog", params={"page_size": 1}).json()["page_size"] == 1
    assert public.get("/api/catalog", params={"page": 0}).status_code == 422


def test_owner_isolation_including_scan_nodes_and_job_actions(api):
    _app, owner, other, public, ids = api
    sid = ids["source"]
    assert public.get("/api/admin/sources").status_code == 401
    assert len(owner.get("/api/admin/sources").json()["items"]) == 1
    assert other.get("/api/admin/sources").json()["items"] == []
    assert other.get(f"/api/admin/sources/{sid}/nodes").status_code == 404
    assert other.patch(f"/api/admin/sources/{sid}", json={"title": "stolen"}).status_code == 404
    assert other.post(f"/api/admin/sources/{sid}/scan", json={}).status_code == 404
    assert other.post(f"/api/admin/jobs/{ids['job']}/retry", json={}).status_code == 404
    assert other.post("/api/admin/recheck", json={"source_id": sid}).status_code == 404
    assert other.get("/api/admin/jobs").json()["items"] == []
    assert other.get("/api/admin/health").json()["items"] == []
    assert owner.get(f"/api/admin/sources/{sid}/nodes").status_code == 200


def test_cookie_encryption_and_no_public_or_admin_response_leak(api):
    app, owner, _other, _public, ids = api
    secret_cookie = "UID=synthetic-secret-cookie; CID=not-real; SEID=not-real"
    result = owner.patch(f"/api/admin/sources/{ids['source']}", json={"credential": secret_cookie})
    assert result.status_code == 200 and result.json()["has_credential"]
    assert secret_cookie not in result.text
    with app.state.database.session() as db:
        stored = db.get(Source, ids["source"]).credential
        assert stored and stored != secret_cookie and "synthetic-secret" not in stored
    for endpoint in ("/api/catalog", "/api/stats", "/api/admin/sources", "/api/admin/audits"):
        response = owner.get(endpoint)
        assert secret_cookie not in response.text
        assert stored not in response.text


def test_two_admin_sources_share_one_work_but_all_versions_retained(api):
    app, owner, other, public, _ids = api
    imported = other.post("/api/admin/import", json={"adapter": "mock", "items": [
        {"url": "https://115.com/s/demob?password=bbbb", "title": "模拟来源乙"}]})
    assert imported.status_code == 201, imported.text
    app.state.worker.drain()
    result = public.get("/api/catalog", params={"q": "星海来信"}).json()
    assert result["total"] == 1
    detail = public.get(f"/api/works/{result['items'][0]['id']}").json()
    assert len(detail["variants"]) == 4
    assert len({x["source_id"] for x in detail["variants"]}) == 2
    assert len(owner.get("/api/admin/sources").json()["items"]) == 1
    assert len(other.get("/api/admin/sources").json()["items"]) == 1


def test_anonymous_suggestion_requires_review_any_admin_can_review_once(api):
    app, owner, other, public, ids = api
    work = public.get("/api/catalog", params={"q": "星海来信"}).json()["items"][0]
    suggested = public.post("/api/suggestions", json={"work_id": work["id"], "changes": {"title": "星海来信·校订"}})
    assert suggested.status_code == 201, suggested.text
    sid = suggested.json()["id"]
    assert public.get(f"/api/works/{work['id']}").json()["title"] == "星海来信"
    assert public.post(f"/api/admin/suggestions/{sid}/review", json={"accept": True}).status_code == 401
    reviewed = other.post(f"/api/admin/suggestions/{sid}/review", json={"accept": True, "reason": "模拟确认"})
    assert reviewed.status_code == 200, reviewed.text
    assert public.get(f"/api/works/{work['id']}").json()["title"] == "星海来信·校订"
    assert owner.post(f"/api/admin/suggestions/{sid}/review", json={"accept": False}).status_code == 409
    with app.state.database.session() as db:
        row = db.get(Suggestion, sid)
        assert row.reviewed_by == ids["other"] and row.status == "accepted"
        assert "title" in db.get(Work, work["id"]).locked
        audit = db.scalar(select(Audit).where(Audit.action == "suggestion.accept"))
        assert audit.admin_id == ids["other"]
        assert audit.before["title"] == "星海来信"
    owner.post(f"/api/admin/sources/{ids['source']}/scan", json={})
    app.state.worker.drain()
    assert public.get(f"/api/works/{work['id']}").json()["title"] == "星海来信·校订"


def test_suggestion_validation_duplicate_and_rate_limit(api):
    _app, _owner, _other, public, _ids = api
    work = public.get("/api/catalog", params={"q": "星海来信"}).json()["items"][0]
    for changes in ({"title": "<script>alert(1)</script>"}, {"poster": "https://127.0.0.1/a"},
                    {"poster": "https://image.tmdb.org/a?token=secret"}, {"visible": False},
                    {"path": "../escape", "variant_id": 1}, {"tmdb_url": "https://example.com/movie/1"}):
        response = public.post("/api/suggestions", json={"work_id": work["id"], "changes": changes})
        assert response.status_code in (400, 422), response.text
    payload = {"work_id": work["id"], "changes": {"year": 2025}}
    assert public.post("/api/suggestions", json=payload).status_code == 201
    assert public.post("/api/suggestions", json=payload).status_code == 409
    for year in (2026, 2027, 2028, 2029):
        assert public.post("/api/suggestions", json={"work_id": work["id"], "changes": {"year": year}}).status_code == 201
    assert public.post("/api/suggestions", json={"work_id": work["id"], "changes": {"year": 2030}}).status_code == 429


def test_search_returns_cached_results_and_only_enqueues_bounded_deduped_checks(api):
    app, _owner, _other, public, _ids = api
    with app.state.database.session.begin() as db:
        for source in db.scalars(select(Source)).all():
            source.checked_at = 0
        for node in db.scalars(select(Node)).all():
            node.checked_at = 0
    before_calls = len(app.state.readers.mock.calls)
    for _ in range(3):
        assert public.get("/api/catalog", params={"q": "星海"}).status_code == 200
    assert len(app.state.readers.mock.calls) == before_calls
    with app.state.database.session() as db:
        tasks = db.scalars(select(Task).where(Task.kind == "health", Task.status == "queued")).all()
        assert len(tasks) == 3  # One source plus at most two version nodes for the result.


def test_real_import_blocked_and_cross_site_write_blocked(api):
    _app, owner, _other, public, _ids = api
    assert owner.post("/api/admin/import", json={"adapter": "live", "items": [
        {"url": "https://115.com/s/syntheticneverrequest?password=aaaa"}]}).status_code == 403
    assert owner.post("/api/admin/import", json={"adapter": "mock", "items": [
        {"url": "https://115.com/s/syntheticneverrequest?password=aaaa"}]}).status_code == 400
    assert owner.post("/api/admin/import/preview", json={"text": "https://115.com/s/demoa?password=aaaa"},
                      headers={"Origin": "https://evil.example"}).status_code == 403
    assert owner.post("/api/logout", data="", headers={"content-type": "text/plain"}).status_code == 415
    assert public.get("/api/does-not-exist").status_code == 404


def test_admin_creation_requires_superuser_and_password_not_returned(api):
    _app, owner, other, _public, _ids = api
    payload = {"username": "third-admin", "password": "third-password-2026"}
    assert other.post("/api/admin/admins", json=payload).status_code == 403
    result = owner.post("/api/admin/admins", json=payload)
    assert result.status_code == 201, result.text
    assert "password" not in result.text
    accounts = owner.get("/api/admin/admins").json()["items"]
    assert any(x["username"] == "third-admin" for x in accounts)
    assert "password" not in json.dumps(accounts)


def test_hidden_file_or_ancestor_only_removes_affected_variants(api):
    app, _owner, other, public, ids = api
    work = public.get("/api/catalog", params={"q": "星海来信"}).json()["items"][0]
    detail_url = f"/api/works/{work['id']}"
    with app.state.database.session.begin() as db:
        source = db.get(Source, ids["source"])
        iso = db.scalar(select(Node).where(Node.name.like("%.iso")))
        for _ in range(app.state.settings.failure_threshold - 1):
            record_health(db, source, iso, "missing", "synthetic missing", app.state.settings)
    assert len(public.get(detail_url).json()["variants"]) == 3  # Pending is not hidden.
    with app.state.database.session.begin() as db:
        source = db.get(Source, ids["source"])
        iso = db.scalar(select(Node).where(Node.name.like("%.iso")))
        record_health(db, source, iso, "missing", "synthetic missing", app.state.settings)
    assert len(public.get(detail_url).json()["variants"]) == 2
    assert public.get("/api/catalog", params={"q": "星海来信", "format": "ISO"}).json()["total"] == 0
    # A second source keeps the work public when source A's ancestor disappears.
    response = other.post("/api/admin/import", json={"adapter": "mock", "items": [
        {"url": "https://115.com/s/demob?password=bbbb", "title": "模拟来源乙"}]})
    assert response.status_code == 201
    app.state.worker.drain()
    with app.state.database.session.begin() as db:
        source = db.get(Source, ids["source"])
        ancestor = db.scalar(select(Node).where(Node.source_id == source.id, Node.name == "林舟作品合集"))
        for _ in range(app.state.settings.failure_threshold):
            record_health(db, source, ancestor, "missing", "synthetic folder missing", app.state.settings)
    remaining = public.get(detail_url).json()["variants"]
    assert len(remaining) == 1 and remaining[0]["source_title"] == "模拟来源乙"
    assert public.get("/api/catalog", params={"q": "星海来信"}).json()["total"] == 1


def test_approved_path_correction_preserves_original_node(api):
    app, _owner, other, public, _ids = api
    work = public.get("/api/catalog", params={"q": "星海来信"}).json()["items"][0]
    variants = public.get(f"/api/works/{work['id']}").json()["variants"]
    variant = variants[0]
    revised = "模拟整理目录/新目录/影片.mkv"
    suggestion = public.post("/api/suggestions", json={"work_id": work["id"],
                              "changes": {"path": revised, "variant_id": variant["id"]}})
    assert suggestion.status_code == 201
    response = other.post(f"/api/admin/suggestions/{suggestion.json()['id']}/review", json={"accept": True})
    assert response.status_code == 200
    updated = public.get(f"/api/works/{work['id']}").json()["variants"]
    item = next(x for x in updated if x["id"] == variant["id"])
    assert item["path"] == revised and item["original_path"] == variant["path"]
    with app.state.database.session() as db:
        assert db.get(Node, variant["node_id"]).path == variant["path"]


def test_configured_source_poster_survives_identification_public_serialization_and_csp(environment):
    database, settings, _readers, _worker, _ids = environment
    settings.public_image_hosts = ("posters.synthetic.example",)
    app = create_app(settings)
    app.state.worker.drain()
    address = "https://posters.synthetic.example/synthetic-poster.jpg"
    with database.session.begin() as db:
        poster = db.scalar(select(Node).where(Node.name == "星海来信-poster.jpg"))
        poster.public_image = address
        source = db.get(Source, poster.source_id)
        db.flush()
        identify_directory(db, source, poster.parent_remote_id, app.state.readers, app.state.worker.tmdb)
    with TestClient(app) as client:
        response = client.get("/api/catalog", params={"q": "星海来信"})
        assert response.status_code == 200
        assert response.json()["items"][0]["info"]["poster"] == address
        assert "https://posters.synthetic.example" in response.headers["content-security-policy"]
    app.state.database.engine.dispose()
