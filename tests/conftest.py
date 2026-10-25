import pytest
from fastapi.testclient import TestClient

from app.adapters import Readers
from app.config import Settings
from app.db import Admin, Database, Source
from app.main import create_app
from app.security import password_hash
from app.worker import Worker, start_scan


@pytest.fixture
def environment(tmp_path, monkeypatch):
    """Isolated file DB survives worker replacement; absolutely no live adapters."""
    def forbidden(*args, **kwargs):
        pytest.fail("offline integration must not make external HTTP requests")
    monkeypatch.setattr("httpx.get", forbidden)
    monkeypatch.setattr("httpx.stream", forbidden)
    settings = Settings(database_url="sqlite:///" + str(tmp_path / "test.db"), secret="s" * 48,
                        live_enabled=False, tmdb_token="", page_size=2, interval=0.1)
    database = Database(settings.database_url)
    database.init()
    readers = Readers(settings, settings.secret)
    worker = Worker(database, settings, readers)
    with database.session.begin() as db:
        admin = Admin(username="test-admin", password_hash=password_hash("test-password-2026"))
        db.add(admin)
        db.flush()
        source = Source(owner_id=admin.id, code="demoa", access_code="aaaa", title="模拟来源甲",
                        url="https://115.com/s/demoa?password=aaaa", adapter="mock")
        db.add(source)
        db.flush()
        job = start_scan(db, source)
        ids = {"admin": admin.id, "source": source.id, "job": job.id}
    yield database, settings, readers, worker, ids
    database.engine.dispose()


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
