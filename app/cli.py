import argparse
import time

from sqlalchemy import func, select

from .adapters import Readers
from .config import Settings
from .db import Admin, Database, SchemaMigration, Source
from .security import password_hash
from .worker import Worker, start_scan


def context(settings=None):
    settings = settings or Settings()
    database = Database(settings.database_url)
    database.init()
    readers = Readers(settings, settings.get_secret())
    return database, settings, readers, Worker(database, settings, readers)


def seed_demo(database, settings, readers, worker):
    """Local explicit demo setup, idempotent; never requests any real resource."""
    settings.tmdb_token = ""
    with database.session.begin() as db:
        for username, password, superuser, code in [
            ("demo", "demo-access-2026", True, "demoa"),
            ("curator", "curator-access-2026", False, "demob"),
        ]:
            user = db.scalar(select(Admin).where(Admin.username == username))
            if not user:
                user = Admin(username=username, password_hash=password_hash(password), superuser=superuser)
                db.add(user)
                db.flush()
            source = db.scalar(select(Source).where(Source.owner_id == user.id, Source.code == code))
            if not source:
                source = Source(owner_id=user.id, code=code, access_code="demo", adapter="mock",
                                title="影视精选 · 模拟分享" if code == "demoa" else "另一管理员 · 模拟版本",
                                url=f"https://115.com/s/{code}?password=demo")
                db.add(source)
                db.flush()
                start_scan(db, source)
    return worker.drain()


def main():
    parser = argparse.ArgumentParser(description="映集 · 本地只读影视索引")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("init-admin")
    admin.add_argument("--username", required=True)
    admin.add_argument("--password", required=True)
    sub.add_parser("migrate", help="应用数据库结构迁移")
    sub.add_parser("seed-demo")
    sub.add_parser("worker")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost", "0.0.0.0"])
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        uvicorn.run("app.main:create_app", factory=True, host=args.host, port=args.port)
        return
    database, settings, readers, worker = context()
    if args.command == "init-admin":
        with database.session.begin() as db:
            if db.scalar(select(Admin).where(Admin.username == args.username)):
                raise SystemExit("管理员已存在；未覆盖其密码")
            db.add(Admin(username=args.username, password_hash=password_hash(args.password), superuser=True))
        print("管理员已建立；请勿在公开环境使用演示账户")
    elif args.command == "migrate":
        # context() has already initialized and upgraded the schema.
        with database.session() as db:
            version = db.scalar(select(func.max(SchemaMigration.version)))
        print(f"数据库迁移已应用；当前版本为 {version}")
    elif args.command == "seed-demo":
        count = seed_demo(database, settings, readers, worker)
        print(f"模拟导入完成，执行 {count} 个任务步骤；没有访问 115 或 TMDB。")
        print("仅本地演示：demo / demo-access-2026；curator / curator-access-2026")
    elif args.command == "worker":
        print("队列 worker 已启动；真实 115 默认禁用，Ctrl+C 退出")
        try:
            while True:
                if not worker.tick():
                    time.sleep(0.4)
        except KeyboardInterrupt:
            print("worker 已停止，检查点保留")


if __name__ == "__main__":
    main()
