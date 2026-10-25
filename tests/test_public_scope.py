"""No real 115 calls: bounded scanning, access states and lease/error fencing."""
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.adapters import P115Reader, ReadError
from app.config import Settings
from app.db import Admin, Database, HealthEvent, Job, Source, Task
from app.health import enqueue_check, record_health
from app.main import create_app
from app.security import password_hash
from app.worker import Worker


@pytest.fixture
def live(tmp_path, monkeypatch):
    settings = Settings(database_url='sqlite:///' + str(tmp_path / 'index.db'),
                        state_dir=str(tmp_path / 'state'), secret='s' * 48,
                        live_enabled=True, interval=0.1, page_size=1)
    app = create_app(settings)
    with app.state.database.session.begin() as db:
        user = Admin(username='public-admin', password_hash=password_hash('synthetic-password'))
        db.add(user)
    calls = []

    def snap(payload):
        calls.append(dict(payload))
        assert payload['cid'] == '0'
        offset = payload['offset']
        return {'state': True, 'data': {'count': 5, 'list': [
            {'cid': str(offset + 1), 'pid': '0', 'n': f'目录{offset}', 's': 1}
        ]}}

    monkeypatch.setattr(app.state.readers.live, 'public_snap', snap)
    with TestClient(app) as client:
        assert client.post('/api/login', json={'username': 'public-admin', 'password': 'synthetic-password'}).status_code == 200
        result = client.post('/api/admin/import', json={'adapter': 'live', 'items': [
            {'url': 'https://115cdn.com/s/demoa?password=aaaa'}]}).json()['items'][0]
        yield app, client, result, calls
    app.state.database.engine.dispose()


def available(app):
    with app.state.database.session.begin() as db:
        for source in db.scalars(select(Source)):
            source.next_request = 0
        for task in db.scalars(select(Task).where(Task.status == 'queued')):
            task.available_at = 0


def test_two_page_budget_survives_pause_restart_and_no_child_tasks(live):
    app, client, ids, calls = live
    assert app.state.worker.tick()
    job_id = ids['job_id']
    assert client.post(f'/api/admin/jobs/{job_id}/pause', json={}).status_code == 200
    assert not app.state.worker.tick()
    assert client.post(f'/api/admin/jobs/{job_id}/resume', json={}).status_code == 200
    available(app)
    restarted = Worker(app.state.database, app.state.settings, app.state.readers)
    assert restarted.tick()
    available(app)
    assert not restarted.tick()
    assert [x['offset'] for x in calls] == [0, 1]
    with app.state.database.session() as db:
        tasks = db.scalars(select(Task)).all()
        assert len(tasks) == 1 and tasks[0].payload['requests'] == 2
        assert tasks[0].payload['truncated']
        assert db.get(Job, job_id).status == 'complete'
        assert db.get(Source, ids['id']).access_status == 'public_listing'
    assert client.get(f"/api/admin/sources/{ids['id']}/nodes").json()['total'] == 2
    assert client.get(f"/api/admin/sources/{ids['id']}/nodes", params={'parent': '1', 'refresh': True}).status_code == 409


def test_viewing_tree_never_enqueues_live_rescan(live):
    app, client, ids, calls = live
    with app.state.database.session.begin() as db:
        db.get(Job, ids['job_id']).status = 'complete'
        db.scalar(select(Task)).status = 'done'
    for _ in range(3):
        assert client.get(f"/api/admin/sources/{ids['id']}/nodes", params={'refresh': True}).status_code == 200
    with app.state.database.session() as db:
        assert len(db.scalars(select(Job)).all()) == 1
        assert len(db.scalars(select(Task)).all()) == 1
    assert calls == []


def test_legacy_child_and_identification_tasks_never_read(live):
    app, _client, ids, calls = live
    with app.state.database.session.begin() as db:
        db.get(Job, ids['job_id']).scan_mode = 'full'  # A legacy migration must remain fail-closed.
        db.scalar(select(Task)).target = '100'
    assert not app.state.worker.tick()
    assert calls == []


def test_request_slot_holds_lock_until_response_done(tmp_path, monkeypatch):
    from contextlib import contextmanager

    reader = P115Reader(Settings(live_enabled=True, state_dir=str(tmp_path)))
    state = {'active': False}

    @contextmanager
    def locked(*args, **kwargs):
        assert not state['active']
        state['active'] = True
        try:
            yield
        finally:
            state['active'] = False

    monkeypatch.setattr('app.adapters.local_file_lock', locked)
    monkeypatch.setattr(reader, 'throttle', lambda: None)

    def snap(payload):
        assert state['active']
        return {'state': True, 'data': {'count': 0, 'list': []}}

    monkeypatch.setattr(reader, 'public_snap', snap)
    assert reader.list_page(SimpleNamespace(code='demoa', access_code='aaaa'), '0', 0, 1) == ([], 0)
    assert not state['active']


@pytest.mark.parametrize('kind,expected', [('auth', 'credential_required'), ('rate_limited', 'rate_limited'),
                                        ('timeout', 'uncertain'), ('incomplete', 'uncertain'),
                                        ('network_error', 'uncertain')])
def test_failures_update_access_state_without_hiding(live, monkeypatch, kind, expected):
    app, _client, ids, _calls = live

    def fail(*args):
        raise ReadError(kind, 'synthetic secret must not be saved')

    monkeypatch.setattr(app.state.readers.live, 'public_snap', fail)
    assert app.state.worker.tick()
    with app.state.database.session() as db:
        source = db.get(Source, ids['id'])
        assert source.access_status == expected and source.failures == 0 and source.health != 'missing'
        task = db.scalar(select(Task))
        assert 'synthetic secret' not in task.error
        if kind == 'rate_limited':
            assert source.next_request >= task.available_at


def test_request_budget_not_reset_by_failure_retry(live, monkeypatch):
    app, client, ids, calls = live

    def fail(payload):
        calls.append(payload)
        raise ReadError('timeout')

    monkeypatch.setattr(app.state.readers.live, 'public_snap', fail)
    for _ in range(2):
        available(app)
        assert app.state.worker.tick()
    assert len(calls) == 2
    assert client.post(f"/api/admin/jobs/{ids['job_id']}/retry", json={}).status_code == 200
    available(app)
    app.state.worker.tick()
    assert len(calls) == 2


def test_nfo_without_cookie_is_auth_and_never_network(tmp_path, monkeypatch):
    reader = P115Reader(Settings(live_enabled=True, state_dir=str(tmp_path)))
    monkeypatch.setattr(reader, 'throttle', lambda: pytest.fail('no request before credential check'))
    node = SimpleNamespace(name='demo.nfo', is_dir=False, size=1)
    with pytest.raises(ReadError) as caught:
        reader.read_nfo(SimpleNamespace(), node, 100)
    assert caught.value.kind == 'auth'


def test_public_http_errors_are_safe_and_do_not_prove_missing(tmp_path, monkeypatch):
    reader = P115Reader(Settings(live_enabled=True, state_dir=str(tmp_path)))
    client_type = httpx.Client
    for status, kind in [(401, 'auth'), (403, 'auth'), (429, 'rate_limited'), (500, 'uncertain'), (302, 'uncertain')]:
        transport = httpx.MockTransport(lambda req, status=status: httpx.Response(status, json={'error': 'hidden-secret'}))
        actual_client = client_type(transport=transport)
        monkeypatch.setattr('app.adapters.httpx.Client', lambda actual_client=actual_client, **kw: actual_client)
        with pytest.raises(ReadError) as caught:
            reader.public_snap({'share_code': 'demoa'})
        assert caught.value.kind == kind and 'hidden-secret' not in str(caught.value)


def test_old_worker_error_cannot_overwrite_new_lease(live, monkeypatch):
    app, _client, ids, _calls = live

    def replaced(*args):
        with app.state.database.session.begin() as db:
            task = db.scalar(select(Task))
            task.lease_token = 'new-worker'
        raise ReadError('auth')

    monkeypatch.setattr(app.state.readers, 'page', replaced)
    assert app.state.worker.tick()
    with app.state.database.session() as db:
        assert db.scalar(select(Task)).lease_token == 'new-worker'
        assert db.get(Source, ids['id']).access_status == 'uncertain'


def test_old_worker_success_rolls_back_node_writes(live, monkeypatch):
    app, _client, ids, _calls = live
    original = app.state.readers.page

    def replaced(*args):
        with app.state.database.session.begin() as db:
            db.scalar(select(Task)).lease_token = 'new-worker'
        return original(*args)

    monkeypatch.setattr(app.state.readers, 'page', replaced)
    assert app.state.worker.tick()
    with app.state.database.session() as db:
        from app.db import Node
        assert db.scalar(select(Node.id)) is None
        assert db.scalar(select(Task)).lease_token == 'new-worker'
        assert db.get(Source, ids['id']).access_status == 'uncertain'


def test_auth_with_credential_has_distinct_status(live, monkeypatch):
    app, _client, ids, _calls = live
    with app.state.database.session.begin() as db:
        db.get(Source, ids['id']).credential = 'encrypted-placeholder'
    monkeypatch.setattr(app.state.readers, 'cookie', lambda source: 'synthetic-cookie')
    monkeypatch.setattr(app.state.readers.live, 'client', lambda cookie: SimpleNamespace(
        share_snap=lambda *args, **kw: {'state': False, 'error': '登录失效'}))
    app.state.worker.tick()
    with app.state.database.session() as db:
        assert db.get(Source, ids['id']).access_status == 'auth_failed'


def test_health_once_no_auto_rechecks_and_missing_threshold(live, monkeypatch):
    app, _client, ids, _calls = live
    with app.state.database.session.begin() as db:
        db.get(Job, ids['job_id']).status = 'paused'
        source = db.get(Source, ids['id'])
        enqueue_check(db, source, settings=app.state.settings, force=True)
    monkeypatch.setattr(app.state.readers.live, 'public_snap', lambda payload: {'state': False, 'error': '分享已取消'})
    assert app.state.worker.tick()
    with app.state.database.session.begin() as db:
        source = db.get(Source, ids['id'])
        assert source.health == 'pending' and source.failures == 1
        assert db.scalar(select(HealthEvent)).result == 'missing'
        assert not db.scalar(select(Task.id).where(Task.kind == 'health', Task.status == 'queued'))
        record_health(db, source, None, 'timeout', '', app.state.settings)
        assert source.failures == 1
        record_health(db, source, None, 'missing', '', app.state.settings)
        assert source.health == 'pending'
        record_health(db, source, None, 'missing', '', app.state.settings)
        assert source.health == 'missing'


def test_schema_v2_keeps_legacy_data(tmp_path):
    database = Database('sqlite:///' + str(tmp_path / 'old.db'))
    with database.engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE sources (id INTEGER PRIMARY KEY, owner_id INTEGER, code TEXT, url TEXT)")
        conn.exec_driver_sql("INSERT INTO sources VALUES (1,1,'demoa','synthetic')")
        conn.exec_driver_sql("CREATE TABLE jobs (id INTEGER PRIMARY KEY, source_id INTEGER, owner_id INTEGER, status TEXT)")
        conn.exec_driver_sql("INSERT INTO jobs VALUES (1,1,1,'paused')")
    database.init()
    database.init()
    assert 'access_status' in {c['name'] for c in inspect(database.engine).get_columns('sources')}
    with database.engine.connect() as conn:
        assert conn.exec_driver_sql('SELECT code,access_status FROM sources').one() == ('demoa','uncertain')
        assert conn.exec_driver_sql('SELECT status,scan_mode FROM jobs').one() == ('paused','full')
    database.engine.dispose()
