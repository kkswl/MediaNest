import math
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .config import local_file_lock
from .fixtures import directory_fixture
from .security import cipher, source_public_image


class ReadError(Exception):
    def __init__(self, kind, message=""):
        super().__init__(message or kind)
        self.kind = kind


class MockReader:
    """Mutable faults only belong to the synthetic adapter; no network operations."""
    def __init__(self):
        self.faults = {}
        self.missing = set()
        self.calls = []

    def list_page(self, source, directory, offset, limit, cookie=""):
        self.calls.append((source.code, directory, offset))
        fault = self.faults.get((source.code, directory, offset)) or self.faults.get((source.code, "*", 0))
        if fault:
            if isinstance(fault, list):
                fault = fault.pop(0) if fault else None
            if fault:
                raise ReadError(fault, "模拟目录响应异常")
        if (source.code, directory) in self.missing:
            raise ReadError("missing", "模拟目录不存在")
        tree, _ = directory_fixture(source.code)
        if directory not in tree:
            raise ReadError("missing", "模拟目录不存在")
        items = [x for x in tree[directory] if (source.code, x["id"]) not in self.missing]
        return items[offset:offset + limit], len(items)

    def read_nfo(self, source, node, limit, cookie=""):
        _, contents = directory_fixture(source.code)
        data = contents.get(node.remote_id, b"")
        if len(data) > limit:
            raise ReadError("oversize", "NFO 超出大小限制")
        return data


class P115Reader:
    """Explicit opt-in, read-only. No receive, move, mkdir or video read API is provided."""
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def request_slot(self):
        """Hold the lock through response completion, not just the start timestamp."""
        if not self.settings.live_enabled:
            raise ReadError("disabled", "真实 115 读取未授权启用")
        try:
            with local_file_lock(Path(self.settings.state_dir) / "115-inflight.lock", timeout=30):
                self.throttle()
                yield
        except (OSError, TimeoutError):
            raise ReadError("timeout", "请求或请求槽位超时，未判资源不存在") from None

    def public_snap(self, payload):
        # One synchronous HTTP request, no implicit client login/retry/redirect.
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=True) as client:
            response = client.get("https://webapi.115.com/share/snap", params=payload)
            if response.status_code == 429:
                raise ReadError("rate_limited", "公开分享接口限流")
            if response.status_code in (401, 403):
                raise ReadError("auth", "公开目录访问需要认证或权限确认")
            if response.status_code != 200:
                raise ReadError("uncertain", "公开分享接口响应未确认")
            return response.json()

    def throttle(self):
        """Global spacing covers every account and every request, including NFO reads.

        All local/container workers MUST share STATE_DIR. This is not a distributed
        cross-host limiter unless the same lock-capable volume is shared.
        No credential, resource URL, NFO or image is written here.
        """
        if not self.settings.live_enabled:
            raise ReadError("disabled", "真实 115 读取未授权启用")
        path = Path(getattr(self.settings, "state_dir", "data")) / "115-request-clock"
        try:
            with local_file_lock(path.with_suffix(".lock")):
                now = time.time()
                previous = float(path.read_text(encoding="ascii")) if path.exists() else 0
                if not math.isfinite(previous) or previous < 0:
                    raise ValueError("invalid clock")
                start = max(now, previous)
                delay = start - now
                if delay > 30:
                    raise ReadError("rate_limited", "全局请求槽位繁忙，稍后重试")
                if delay:
                    # Keep the OS lock while waiting so later workers cannot overtake
                    # a delayed reservation and bunch requests into the same instant.
                    time.sleep(delay)
                start = time.time()
                # Atomic replace under the shared lock; a crash cannot leave partial digits.
                temporary = path.with_suffix(f".{os.getpid()}.tmp")
                with temporary.open("w", encoding="ascii") as handle:
                    handle.write(str(start + max(0.1, self.settings.interval)))
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary.replace(path)
        except ReadError:
            raise
        except (OSError, ValueError, TimeoutError):
            raise ReadError("rate_limited", "全局请求时钟不可用；已停止真实请求") from None

    def client(self, cookie):
        if not self.settings.live_enabled:
            raise ReadError("disabled", "真实 115 读取未授权启用")
        if not cookie:
            raise ReadError("auth", "该操作需要管理员配置私有 115 凭据")
        from p115client import P115Client
        # Fixed 0.0.9.7.2 has no check_for_relogin parameter. A non-None cookie
        # initializes only; never construct with None (which starts QR login).
        return P115Client(cookie, console_qrcode=False)

    def response(self, data):
        if not isinstance(data, dict):
            raise ReadError("uncertain", "响应结构异常")
        if data.get("state") not in (True, 1):
            code = str(data.get("errno", data.get("errNo", "")))
            code = code[:30] if code.isdigit() else "unknown"
            message = str(data.get("error") or data.get("message") or data.get("msg") or "").lower()
            # PanSou check115 is a design reference, but its broad `bad` fallback
            # would hide rate-limit/auth failures. Use only narrow explicit evidence.
            if any(x in message for x in ("密码", "提取码", "访问码", "receive_code")):
                kind = "locked"
            elif any(x in message for x in ("登录", "账号", "账户", "cookie", "认证", "token")):
                kind = "auth"
            elif any(x in message for x in ("频繁", "限流", "验证码", "风控", "频率", "rate limit")):
                kind = "rate_limited"
            elif any(x in message for x in ("分享已取消", "分享已过期", "分享不存在", "分享已失效",
                                            "分享已删除", "文件不存在", "目录不存在")):
                kind = "missing"
            else:
                kind = "auth" if code == "990009" else "uncertain"
            raise ReadError(kind, f"115 读取失败，代码 {code}")
        result = data.get("data")
        if not isinstance(result, dict):
            raise ReadError("uncertain", "缺少目录响应数据")
        # Restricted/abnormal share states cannot prove a node disappeared.
        info = result.get("shareinfo") or {}
        if not isinstance(info, dict) or info.get("forbid_reason"):
            raise ReadError("locked", "分享访问受限，未判资源不存在")
        share_state = result.get("share_state", info.get("share_state", 0))
        if share_state not in (0, 1, "0", "1", None):
            raise ReadError("uncertain", "分享状态异常，待人工复检")
        return result

    def list_page(self, source, directory, offset, limit, cookie=""):
        try:
            if not str(directory).isdigit() or offset < 0 or not 1 <= limit <= 10000:
                raise ReadError("uncertain", "目录分页请求参数异常")
            payload = {"share_code": source.code, "receive_code": source.access_code,
                       "cid": directory, "offset": offset, "limit": limit}
            with self.request_slot():
                if cookie:
                    raw = self.client(cookie).share_snap(payload, timeout=20)
                else:
                    raw = self.public_snap(payload)
            data = self.response(raw)
            if not isinstance(data.get("list"), list) or "count" not in data:
                raise ReadError("incomplete", "缺少完整分页信息")
            output = []
            for x in data["list"]:
                if not isinstance(x, dict):
                    raise ReadError("uncertain", "节点结构异常")
                is_dir = "fid" not in x
                rid = x.get("cid") if is_dir else x.get("fid")
                parent = x.get("pid") if is_dir else x.get("cid")
                name = x.get("n")
                if (not str(rid).isdigit() or int(rid) <= 0 or not isinstance(name, str)
                        or not name or len(name) > 10000 or "/" in name or "\\" in name
                        or str(parent) != str(directory)):
                    raise ReadError("uncertain", "节点缺少 ID 或名称")
                size = int(x.get("s", 0))
                if size < 0:
                    raise ReadError("uncertain", "节点大小异常")
                image = source_public_image(x.get("thumb_url") or x.get("thumb") or "",
                                            getattr(self.settings, "public_image_hosts", ()))
                output.append({"id": str(rid), "parent": str(directory), "name": name,
                               "is_dir": is_dir, "size": size,
                               "sha1": str(x.get("sha", "")), "public_image": image})
            total = int(data["count"])
            if (total < 0 or len(output) > limit or (not output and offset < total)
                    or (output and offset + len(output) > total)
                    or len({x["id"] for x in output}) != len(output)):
                raise ReadError("incomplete", "分页数据不完整或总数异常")
            return output, total
        except ReadError:
            raise
        except (httpx.TimeoutException, TimeoutError):
            raise ReadError("timeout", "115 请求超时，未判资源不存在") from None
        except httpx.TransportError:
            raise ReadError("network_error", "115 网络异常，未判资源不存在") from None
        except Exception as e:
            # Never leak exception text containing URLs, cookies or request headers.
            raise ReadError("uncertain", f"115 请求未确认（{type(e).__name__}）") from None

    def read_nfo(self, source, node, limit, cookie=""):
        if not node.name.lower().endswith(".nfo") or node.is_dir or not 0 <= node.size <= limit:
            raise ReadError("oversize", "仅允许体积受限的 NFO")
        try:
            client = self.client(cookie)
            with self.request_slot():
                link = client.share_download_url({"share_code": source.code, "receive_code": source.access_code,
                                                  "file_id": node.remote_id}, timeout=20)
            # A changed/misbound download result must not turn a small sidecar read
            # into reading unrelated or large content. P115URL exposes these fields.
            if (str(getattr(link, "id", "")) != str(node.remote_id)
                    or getattr(link, "name", "") != node.name or getattr(link, "is_dir", True)
                    or not 0 <= int(getattr(link, "size", -1)) <= limit):
                raise ReadError("uncertain", "NFO 下载引用与目标节点不一致")
            address = str(link)
            p = urlsplit(address)
            host = (p.hostname or "").lower()
            if (p.scheme != "https" or not host.endswith((".115.com", ".115cdn.com"))
                    or p.username or p.password or p.port not in (None, 443) or p.fragment
                    or re.search(r"[\s\x00-\x1f\\]", address)):
                raise ReadError("uncertain", "NFO 地址域名未在只读白名单内")
            with self.request_slot(), httpx.stream("GET", address, headers={"Accept-Encoding": "identity"},
                              timeout=20, follow_redirects=False, trust_env=False) as r:
                if r.status_code != 200:
                    raise ReadError("uncertain", "NFO 读取失败")
                declared = r.headers.get("content-length")
                if declared is not None and (not declared.isdigit() or int(declared) > limit):
                    raise ReadError("oversize", "NFO 声明长度超出上限")
                data = bytearray()
                for chunk in r.iter_bytes(8192):
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ReadError("oversize", "NFO 超过内存读取上限")
                return bytes(data)
        except ReadError:
            raise
        except (httpx.TimeoutException, TimeoutError):
            raise ReadError("timeout", "NFO 请求超时，未判资源不存在") from None
        except Exception as e:
            raise ReadError("uncertain", f"NFO 请求未确认（{type(e).__name__}）") from None


class Readers:
    def __init__(self, settings, secret):
        self.settings = settings
        self.secret = secret
        self.mock = MockReader()
        self.live = P115Reader(settings)

    def reader(self, source):
        if source.adapter not in ("mock", "live"):
            raise ReadError("disabled", "未知来源适配器")
        return self.mock if source.adapter == "mock" else self.live

    def cookie(self, source):
        if not source.credential:
            return ""
        return cipher(self.secret).decrypt(source.credential.encode()).decode()

    def page(self, source, directory, offset, limit):
        try:
            cookie = self.cookie(source)
            result = self.reader(source).list_page(source, directory, offset, limit, cookie)
        except ReadError as exc:
            access_failure(source, exc.kind)
            raise
        if source.adapter == "live":
            source.access_status = "credential_listing" if cookie else "public_listing"
        return result

    def nfo(self, source, node):
        try:
            return self.reader(source).read_nfo(source, node, self.settings.nfo_limit, self.cookie(source))
        except ReadError as exc:
            access_failure(source, exc.kind)
            raise


def access_failure(source, kind):
    if source.adapter == "live":
        source.access_status = (("auth_failed" if source.credential else "credential_required")
                                if kind in ("auth", "auth_failed") else
                                "rate_limited" if kind == "rate_limited" else "uncertain")
