import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.db import Database, Job, Task


def test_schema_upgrade_adds_version_and_new_account_columns(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE admins (id INTEGER PRIMARY KEY, username VARCHAR(80) UNIQUE NOT NULL, "
        "password_hash TEXT NOT NULL, superuser BOOLEAN NOT NULL DEFAULT 0, active BOOLEAN NOT NULL DEFAULT 1);"
        "CREATE TABLE sessions (digest VARCHAR(64) PRIMARY KEY, admin_id INTEGER NOT NULL, expires FLOAT NOT NULL);"
    )
    connection.close()
    database = Database("sqlite:///" + str(path))
    database.init()
    columns = {column["name"] for column in inspect(database.engine).get_columns("admins")}
    session_columns = {column["name"] for column in inspect(database.engine).get_columns("sessions")}
    assert {"created_at"} <= columns
    assert {"created_at", "revoked"} <= session_columns
    with database.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version FROM schema_migrations").scalar() == 1
    database.engine.dispose()


def test_import_conflict_and_csrf_double_submit(api):
    _app, owner, _other, _public, _ids = api
    conflict = owner.post("/api/admin/import", json={"adapter": "mock", "items": [
        {"url": "https://115.com/s/demoa?password=aaaa", "access_code": "bbbb"}]})
    assert conflict.status_code == 400
    token = owner.cookies.get("csrf_token")
    assert token
    blocked = owner.post("/api/admin/import/preview", json={"text": "https://115.com/s/demoa?password=aaaa"},
                         headers={"Origin": "http://testserver"})
    assert blocked.status_code == 403
    allowed = owner.post("/api/admin/import/preview", json={"text": "https://115.com/s/demoa?password=aaaa"},
                         headers={"Origin": "http://testserver", "X-CSRF-Token": token})
    assert allowed.status_code == 200


def test_cancel_propagates_to_queued_tasks_and_audit_redacts_share_code(api):
    app, owner, _other, _public, ids = api
    created = owner.post(f"/api/admin/sources/{ids['source']}/scan", json={})
    assert created.status_code == 200
    job_id = created.json()["job_id"]
    cancelled = owner.post(f"/api/admin/jobs/{job_id}/cancel", json={})
    assert cancelled.status_code == 200
    with app.state.database.session() as db:
        job = db.get(Job, job_id)
        tasks = db.scalars(select(Task).where(Task.job_id == job_id)).all()
        assert job.status == "cancelled"
        assert tasks and all(task.status == "cancelled" for task in tasks)
    updated = owner.patch(f"/api/admin/sources/{ids['source']}", json={"title": "新名称"})
    assert updated.status_code == 200
    audits = owner.get("/api/admin/audits")
    assert audits.status_code == 200
    assert "password=aaaa" not in audits.text


def test_resume_finalizes_idle_paused_job(api):
    app, owner, _other, _public, ids = api
    created = owner.post(f"/api/admin/sources/{ids['source']}/scan", json={})
    job_id = created.json()["job_id"]
    with app.state.database.session.begin() as db:
        job = db.get(Job, job_id)
        job.status = "paused"
        for task in db.scalars(select(Task).where(Task.job_id == job_id)).all():
            task.status = "done"
    resumed = owner.post(f"/api/admin/jobs/{job_id}/resume", json={})
    assert resumed.status_code == 200 and resumed.json()["status"] == "complete"


def test_admin_deactivation_revokes_login(api):
    _app, owner, _other, _public, _ids = api
    created = owner.post("/api/admin/admins", json={"username": "temporary-admin",
                                                   "password": "temporary-password-2026"})
    assert created.status_code == 201
    admin_id = created.json()["id"]
    changed = owner.patch(f"/api/admin/admins/{admin_id}", json={"active": False})
    assert changed.status_code == 200
    with TestClient(_app) as client:
        assert client.post("/api/login", json={"username": "temporary-admin",
                                                "password": "temporary-password-2026"}).status_code == 401
