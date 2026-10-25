import time
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    superuser = Column(Boolean, default=False, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)


class SessionToken(Base):
    __tablename__ = "sessions"
    digest = Column(String(64), primary_key=True)
    admin_id = Column(ForeignKey("admins.id"), nullable=False)
    expires = Column(Float, nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"
    version = Column(Integer, primary_key=True)
    applied_at = Column(Float, default=time.time, nullable=False)


class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True)
    owner_id = Column(ForeignKey("admins.id"), nullable=False, index=True)
    code = Column(String(120), nullable=False)
    access_code = Column(String(100), default="")
    url = Column(Text, nullable=False)
    title = Column(String(500), default="")
    adapter = Column(String(20), default="mock", nullable=False)
    credential = Column(Text, default="")
    access_status = Column(String(40), default="uncertain", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    health = Column(String(30), default="unchecked", nullable=False)
    failures = Column(Integer, default=0, nullable=False)
    checked_at = Column(Float, default=0)
    last_scan = Column(Float, default=0)
    next_request = Column(Float, default=0)
    created_at = Column(Float, default=time.time)
    __table_args__ = (UniqueConstraint("owner_id", "code"),)


class Node(Base):
    __tablename__ = "nodes"
    id = Column(Integer, primary_key=True)
    source_id = Column(ForeignKey("sources.id"), nullable=False, index=True)
    remote_id = Column(String(120), nullable=False)
    parent_remote_id = Column(String(120), nullable=False, index=True)
    name = Column(Text, nullable=False)
    path = Column(Text, nullable=False)
    is_dir = Column(Boolean, nullable=False)
    size = Column(Float, default=0)
    sha1 = Column(String(100), default="")
    public_image = Column(Text, default="")
    health = Column(String(30), default="healthy", nullable=False)
    failures = Column(Integer, default=0, nullable=False)
    checked_at = Column(Float, default=0)
    last_scan = Column(Float, default=time.time)
    __table_args__ = (UniqueConstraint("source_id", "remote_id"),)


class Work(Base):
    __tablename__ = "works"
    id = Column(Integer, primary_key=True)
    identity = Column(String(200), unique=True, nullable=False)
    title = Column(String(500), nullable=False, index=True)
    year = Column(Integer, nullable=True, index=True)
    category = Column(String(30), default="movie", index=True)
    status = Column(String(30), default="review", index=True)
    visible = Column(Boolean, default=True, nullable=False)
    info = Column(JSON, default=dict, nullable=False)
    provenance = Column(JSON, default=dict, nullable=False)
    locked = Column(JSON, default=list, nullable=False)
    updated_at = Column(Float, default=time.time)


class Variant(Base):
    __tablename__ = "variants"
    id = Column(Integer, primary_key=True)
    work_id = Column(ForeignKey("works.id"), nullable=False, index=True)
    source_id = Column(ForeignKey("sources.id"), nullable=False, index=True)
    node_id = Column(ForeignKey("nodes.id"), unique=True, nullable=False)
    attributes = Column(JSON, default=dict, nullable=False)
    season = Column(Integer, nullable=True)
    episodes = Column(JSON, default=list, nullable=False)
    resource_group = Column(String(300), default="")


class Person(Base):
    __tablename__ = "people"
    id = Column(Integer, primary_key=True)
    name = Column(String(300), unique=True, nullable=False)


class WorkPerson(Base):
    __tablename__ = "work_people"
    work_id = Column(ForeignKey("works.id"), primary_key=True)
    person_id = Column(ForeignKey("people.id"), primary_key=True)


class Collection(Base):
    __tablename__ = "collections"
    id = Column(Integer, primary_key=True)
    name = Column(String(500), nullable=False)
    kind = Column(String(40), nullable=False)
    __table_args__ = (UniqueConstraint("name", "kind"),)


class WorkCollection(Base):
    __tablename__ = "work_collections"
    work_id = Column(ForeignKey("works.id"), primary_key=True)
    collection_id = Column(ForeignKey("collections.id"), primary_key=True)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    source_id = Column(ForeignKey("sources.id"), nullable=False, index=True)
    owner_id = Column(ForeignKey("admins.id"), nullable=False)
    status = Column(String(30), default="queued", nullable=False)
    scan_mode = Column(String(30), default="full", nullable=False)
    scope_node_id = Column(Integer, nullable=True)
    scope_remote_id = Column(String(120), default="0", nullable=False)
    scope_path = Column(Text, default="", nullable=False)
    scan_requests = Column(Integer, default=0, nullable=False)
    pages_read = Column(Integer, default=0, nullable=False)
    nodes_read = Column(Integer, default=0, nullable=False)
    created_at = Column(Float, default=time.time)
    finished_at = Column(Float, nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    dedupe_key = Column(String(250), nullable=True, unique=True)
    job_id = Column(ForeignKey("jobs.id"), nullable=True, index=True)
    source_id = Column(ForeignKey("sources.id"), nullable=False, index=True)
    kind = Column(String(30), nullable=False)
    target = Column(String(150), nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    status = Column(String(30), default="queued", nullable=False, index=True)
    available_at = Column(Float, default=0, nullable=False, index=True)
    lease_until = Column(Float, default=0, nullable=False)
    lease_token = Column(String(80), default="")
    attempts = Column(Integer, default=0, nullable=False)
    error = Column(Text, default="")
    updated_at = Column(Float, default=time.time)


class HealthEvent(Base):
    __tablename__ = "health_events"
    id = Column(Integer, primary_key=True)
    source_id = Column(ForeignKey("sources.id"), nullable=False, index=True)
    node_id = Column(ForeignKey("nodes.id"), nullable=True)
    result = Column(String(40), nullable=False)
    state = Column(String(30), nullable=False)
    reason = Column(Text, default="")
    at = Column(Float, default=time.time)


class Suggestion(Base):
    __tablename__ = "suggestions"
    id = Column(Integer, primary_key=True)
    work_id = Column(ForeignKey("works.id"), nullable=False, index=True)
    changes = Column(JSON, nullable=False)
    status = Column(String(30), default="pending", nullable=False)
    reviewed_by = Column(ForeignKey("admins.id"), nullable=True)
    reason = Column(Text, default="")
    created_at = Column(Float, default=time.time)


class Audit(Base):
    __tablename__ = "audits"
    id = Column(Integer, primary_key=True)
    admin_id = Column(ForeignKey("admins.id"), nullable=False)
    action = Column(String(80), nullable=False)
    target = Column(String(120), nullable=False)
    before = Column(JSON, default=dict)
    after = Column(JSON, default=dict)
    at = Column(Float, default=time.time)


class RateBucket(Base):
    __tablename__ = "rate_buckets"
    key = Column(String(200), primary_key=True)
    window = Column(Integer, nullable=False)
    hits = Column(Integer, default=1, nullable=False)


class Database:
    def __init__(self, url):
        if url.startswith("sqlite:///"):
            p = url.removeprefix("sqlite:///")
            if p != ":memory:":
                Path(p).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 20}
                                    if url.startswith("sqlite") else {}, pool_pre_ping=True)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def sqlite_setup(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def init(self):
        Base.metadata.create_all(self.engine)
        # The repository intentionally keeps migrations small and explicit.  The
        # baseline is created by SQLAlchemy, while these ALTER statements make
        # upgrades from the first prototype safe without dropping user data.
        from sqlalchemy import inspect, text

        with self.engine.begin() as connection:
            inspector = inspect(connection)
            additions = {
                "sources": [("access_status", "VARCHAR(40) NOT NULL DEFAULT 'uncertain'")],
                "jobs": [("scan_mode", "VARCHAR(30) NOT NULL DEFAULT 'full'"),
                         ("scope_node_id", "INTEGER"),
                         ("scope_remote_id", "VARCHAR(120) NOT NULL DEFAULT '0'"),
                         ("scope_path", "TEXT NOT NULL DEFAULT ''"),
                         ("scan_requests", "INTEGER NOT NULL DEFAULT 0"),
                         ("pages_read", "INTEGER NOT NULL DEFAULT 0"),
                         ("nodes_read", "INTEGER NOT NULL DEFAULT 0")],
                "admins": [("created_at", "FLOAT NOT NULL DEFAULT 0")],
                "sessions": [
                    ("created_at", "FLOAT NOT NULL DEFAULT 0"),
                    ("revoked", "BOOLEAN NOT NULL DEFAULT FALSE"),
                ],
            }
            for table, columns in additions.items():
                present = {column["name"] for column in inspector.get_columns(table)}
                for name, definition in columns:
                    if name not in present:
                        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
            if connection.execute(text("SELECT 1 FROM schema_migrations WHERE version = 1")).first() is None:
                connection.execute(text("INSERT INTO schema_migrations (version, applied_at) VALUES (1, :at)"),
                                   {"at": time.time()})
            if connection.execute(text("SELECT 1 FROM schema_migrations WHERE version = 2")).first() is None:
                connection.execute(text("INSERT INTO schema_migrations (version, applied_at) VALUES (2, :at)"),
                                   {"at": time.time()})
            if connection.execute(text("SELECT 1 FROM schema_migrations WHERE version = 3")).first() is None:
                connection.execute(text("INSERT INTO schema_migrations (version, applied_at) VALUES (3, :at)"),
                                   {"at": time.time()})
