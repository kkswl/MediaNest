"""Bounded single-worker smoke test. Never embed real inputs in this file.

One loopback API process and one synchronous worker (the caller). No thread pool,
recursive discovery, media/NFO reads, saved credentials or raw-response output.
"""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from sqlalchemy import select

from app.adapters import Readers
from app.config import Settings
from app.db import Admin, Database, HealthEvent, Job, Node, Source, Task
from app.health import enqueue_check
from app.security import parse_import, password_hash
from app.worker import Worker


def inputs(demo):
    if demo:
        return 'https://115cdn.com/s/demoa', 'aaaa'
    share = os.getenv('REAL_SHARE_URL', '')
    code = os.getenv('REAL_ACCESS_CODE', '')
    if not share or not code:
        raise ValueError('请先提供 REAL_SHARE_URL 和 REAL_ACCESS_CODE；没有发起请求')
    parsed = parse_import(share)
    if (len(parsed) != 1 or parsed[0]['conflict'] or
            parsed[0]['access_code'] not in ('', code)):
        raise ValueError('仅接受一个访问码一致的授权来源；没有发起请求')
    return share, code


def check_response(response):
    if response.status_code >= 300:
        # Do not include upstream/local response bodies, URLs or query strings.
        raise RuntimeError('本地 API 操作未成功，HTTP ' + str(response.status_code))
    return response.json()


def run(demo=False):
    share, code = inputs(demo)
    report = {'real_115': not demo, 'proxy_configured': bool(os.getenv('HTTPS_PROXY')),
              'serial_115': True, 'requests': 0, 'scan_requests': 0, 'health_requests': 0,
              'pages': 0, 'nodes': 0, 'health': 'not_run', 'remote_writes': False,
              'tmdb': False, 'cookie_used': False}
    root = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix='medianest-public-') as directory:
        settings = Settings(database_url='sqlite:///' + str(Path(directory) / 'index.db'),
                            state_dir=str(Path(directory) / 'state'), secret=secrets.token_urlsafe(48),
                            live_enabled=True, live_root_only=True, tmdb_enabled=False,
                            tmdb_token='', page_size=50, interval=max(2, Settings().interval))
        database = Database(settings.database_url)
        database.init()
        password = secrets.token_urlsafe(32)
        with database.session.begin() as db:
            db.add(Admin(username='verify-local', password_hash=password_hash(password), superuser=True))
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        env = {k: v for k, v in os.environ.items() if not k.startswith(('REAL_', 'OTEL_'))}
        env.update(DATABASE_URL=settings.database_url, STATE_DIR=settings.state_dir,
                   APP_SECRET=settings.secret, ENABLE_LIVE_115='yes-I-authorize',
                   ENABLE_TMDB='no', TMDB_TOKEN='', LIVE_ROOT_ONLY='yes')
        process = None
        try:
            process = subprocess.Popen(
                [sys.executable, '-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1',
                 '--port', str(port), '--no-access-log', '--log-level', 'critical'],
                cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=20, trust_env=False) as client:
                deadline = time.monotonic() + 15
                while True:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('本地单 API 未就绪')
                    try:
                        if client.get('/api/stats').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                check_response(client.post('/api/login', json={'username': 'verify-local', 'password': password}))
                imported = check_response(client.post('/api/admin/import', json={
                    'adapter': 'live', 'scan_mode': 'root_preview',
                    'items': [{'url': share, 'access_code': code, 'title': '临时只读验证'}]}))['items'][0]
                source_id, job_id = imported['id'], imported['job_id']
                readers = Readers(settings, settings.secret)
                actual_snap = readers.live.public_snap
                stage = 'scan'

                def bounded_snap(payload):
                    key, limit = ('scan_requests', 2) if stage == 'scan' else ('health_requests', 1)
                    if payload['cid'] != '0' or report[key] >= limit:
                        raise RuntimeError('请求预算或目录边界已触发')
                    report[key] += 1
                    report['requests'] += 1
                    if demo:
                        raw = {'state': True, 'data': {'count': 1, 'list': [
                            {'cid': '100', 'pid': '0', 'n': '虚构目录', 's': 1}]}}
                    else:
                        raw = actual_snap(payload)
                    body = raw.get('data', {}) if isinstance(raw, dict) else {}
                    info = body.get('shareinfo', {}) if isinstance(body, dict) else {}
                    report['title_field_present'] = bool(info.get('share_title'))
                    report['capacity_field_present'] = 'file_size' in info
                    if stage == 'scan' and raw.get('state') is True:
                        report['pages'] += 1
                    return raw

                readers.live.public_snap = bounded_snap
                worker = Worker(database, settings, readers)
                # No background daemon: exactly one tick at a time, at most two scan requests.
                while report['scan_requests'] < 2:
                    with database.session() as db:
                        task = db.scalar(select(Task).where(Task.job_id == job_id, Task.kind == 'scan'))
                        if task is None or task.status not in ('queued', 'running'):
                            break
                        wait = max(0, task.available_at - time.time(), db.get(Source, source_id).next_request - time.time())
                    if wait:
                        time.sleep(min(wait, 30))
                    if not worker.tick():
                        break
                    with database.session() as db:
                        task = db.scalar(select(Task).where(Task.job_id == job_id, Task.kind == 'scan'))
                        if task.error:
                            report['scan_failure'] = task.error.split(':', 1)[0]
                            break  # No repeated live regression on a failing endpoint.
                with database.session() as db:
                    job = db.get(Job, job_id)
                    report['scan_status'] = job.status
                if report['scan_status'] in ('queued', 'running'):
                    check_response(client.post(f'/api/admin/jobs/{job_id}/pause', json={}))
                    report['scan_status'] = 'paused'
                nodes = check_response(client.get(f'/api/admin/sources/{source_id}/nodes'))
                report['nodes'] = nodes['total']
                report['node_fields'] = sorted(nodes['items'][0]) if nodes['items'] else []
                with database.session() as db:
                    report['stored_nodes'] = len(db.scalars(select(Node).where(Node.source_id == source_id)).all())
                stage = 'health'
                with database.session.begin() as db:
                    source = db.get(Source, source_id)
                    # Manual one-shot health request. No automatic pending rechecks in preview mode.
                    enqueue_check(db, source, settings=settings, force=True)
                    source.next_request = 0
                worker.tick()
                with database.session() as db:
                    events = db.scalars(select(HealthEvent).order_by(HealthEvent.id.desc())).all()
                    report['health'] = events[0].result if events else 'not_run'
                    report['access_status'] = db.get(Source, source_id).access_status
                check_response(client.post('/api/logout', json={}))
        finally:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            database.engine.dispose()
            # TemporaryDirectory removes only this unique temporary DB and limiter state.
    report['temporary_state_removed'] = not Path(directory).exists()
    return report


def main():
    parser = argparse.ArgumentParser(description='单 API + 单 worker 根目录只读限页烟测')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--offline-demo', action='store_true', help='仅用虚构目录，不请求 115')
    mode.add_argument('--confirm-real-read', action='store_true', help='明确执行一次已授权来源的限页验证')
    args = parser.parse_args()
    try:
        result = run(demo=args.offline_demo)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 -- the CLI boundary must redact arbitrary transport errors
        # Exception text may contain request URLs or response content; never print it.
        print(json.dumps({'status': 'failed', 'exception_type': type(exc).__name__,
                          'detail': '检查唯一来源参数、代理及本地运行条件；未输出敏感内容'}, ensure_ascii=False))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
