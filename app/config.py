import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path


@contextmanager
def local_file_lock(path, timeout=30):
    """OS-backed lock, released on process death; no stale-lock-file deletion."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        acquired = False
        while not acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("本地共享锁等待超时") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///data/yingji.db"))
    secret: str = field(default_factory=lambda: os.getenv("APP_SECRET", ""))
    live_enabled: bool = field(default_factory=lambda: os.getenv("ENABLE_LIVE_115") == "yes-I-authorize")
    tmdb_enabled: bool = field(default_factory=lambda: os.getenv("ENABLE_TMDB") == "yes-I-authorize")
    tmdb_token: str = field(default_factory=lambda: os.getenv("TMDB_TOKEN", ""))
    state_dir: str = field(default_factory=lambda: os.getenv("STATE_DIR", "data"))
    public_image_hosts: tuple = field(default_factory=lambda: tuple(
        h.strip().lower() for h in os.getenv("PUBLIC_SOURCE_IMAGE_HOSTS", "").split(",") if h.strip()))
    failure_threshold: int = field(default_factory=lambda: max(3, int(os.getenv("FAILURE_THRESHOLD", "3"))))
    page_size: int = field(default_factory=lambda: max(1, min(500, int(os.getenv("SCAN_PAGE_SIZE", "50")))))
    interval: float = field(default_factory=lambda: max(0.1, float(os.getenv("REQUEST_INTERVAL", "2"))))
    # Safe live default: even legacy full jobs are restricted at the worker boundary.
    live_root_only: bool = field(default_factory=lambda: os.getenv("LIVE_ROOT_ONLY", "yes") != "no")
    health_ttl: float = 3600
    recheck_delay: float = 60
    nfo_limit: int = 262144
    task_lease: float = 120

    def get_secret(self):
        if self.secret:
            if len(self.secret) < 32:
                raise ValueError("APP_SECRET 至少 32 字符")
            return self.secret
        from secrets import token_urlsafe
        path = Path(self.state_dir) / "app-secret"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Every reader holds this lock; no process can observe a partially written secret.
        with local_file_lock(path.with_suffix(".lock")):
            try:
                with path.open("x", encoding="utf-8") as f:
                    f.write(token_urlsafe(48))
                    f.flush()
                    os.fsync(f.fileno())
                path.chmod(0o600)
            except FileExistsError:
                pass
            value = path.read_text(encoding="utf-8").strip()
            if len(value) < 32:
                raise ValueError("持久化密钥无效；请恢复原密钥，不能自动轮换已加密凭据")
            return value
