"""A real loopback socket test; TestClient can mask response/commit ordering races."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def test_real_http_write_is_committed_before_response(environment, tmp_path):
    _database, settings, _readers, worker, ids = environment
    worker.drain()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith("OTEL_")}
    env.update(DATABASE_URL=settings.database_url, APP_SECRET=settings.secret,
               ENABLE_LIVE_115="no", ENABLE_TMDB="no", TMDB_TOKEN="", STATE_DIR=str(tmp_path / "state"))
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "error"],
        cwd=Path(__file__).resolve().parent.parent, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False) as client:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    pytest.fail("local test server terminated: " + process.communicate()[1].decode(errors="replace"))
                try:
                    ready = client.get("/api/stats")
                    if ready.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if time.monotonic() > deadline:
                    pytest.fail("local test server did not start in 15 seconds")
                time.sleep(0.05)
            # Keep reusing the HTTP connection: no sleeps between write and read.
            for _ in range(5):
                login = client.post("/api/login", json={"username": "test-admin", "password": "test-password-2026"})
                assert login.status_code == 200, login.text
                me = client.get("/api/me")
                assert me.status_code == 200, me.text
                assert me.json()["username"] == "test-admin"
                logout = client.post("/api/logout", json={})
                assert logout.status_code == 200
                assert client.get("/api/me").status_code == 401
            assert client.post("/api/login", json={"username": "test-admin", "password": "test-password-2026"}).status_code == 200
            changed = client.patch(f"/api/admin/sources/{ids['source']}", json={"title": "立即提交已落库"})
            assert changed.status_code == 200, changed.text
            sources = client.get("/api/admin/sources").json()["items"]
            assert next(x for x in sources if x["id"] == ids["source"])["title"] == "立即提交已落库"
            work = client.get("/api/catalog", params={"q": "星海来信"}).json()["items"][0]
            suggested = client.post("/api/suggestions", json={"work_id": work["id"], "changes": {"year": 2027}})
            assert suggested.status_code == 201, suggested.text
            reviewed = client.post(f"/api/admin/suggestions/{suggested.json()['id']}/review", json={"accept": True})
            assert reviewed.status_code == 200, reviewed.text
            assert client.get(f"/api/works/{work['id']}").json()["year"] == 2027
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
