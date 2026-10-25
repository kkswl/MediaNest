import base64
import hashlib
import hmac
import ipaddress
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .db import RateBucket


def password_hash(password):
    if len(password) < 12 or len(password) > 200:
        raise ValueError("密码须为 12–200 字符")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + digest).decode()


def password_valid(password, hashed):
    try:
        raw = base64.b64decode(hashed)
        computed = hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1)
        return hmac.compare_digest(raw[16:], computed)
    except (ValueError, TypeError):
        return False


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def cipher(secret):
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def safe_url(value, image=False, tmdb=False):
    if not value:
        return ""
    if len(value) > 2000:
        raise ValueError("网址过长")
    p = urlsplit(value)
    host = (p.hostname or "").lower()
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        raise ValueError("仅支持无认证的 HTTPS 网址")
    if re.search(r"[\s\x00-\x1f\\]", value):
        raise ValueError("无效网址")
    try:
        ipaddress.ip_address(host)
        raise ValueError("不接受 IP 地址")
    except ValueError as e:
        if str(e) == "不接受 IP 地址":
            raise
    if not host or host == "localhost" or "." not in host or host.endswith((".local", ".internal")):
        raise ValueError("不接受内部地址")
    if tmdb and (host not in ("www.themoviedb.org", "themoviedb.org")
                 or not re.match(r"^/(movie|tv)/\d+(?:-[^/]*)?/?$", p.path) or p.query):
        raise ValueError("请输入 TMDB 电影或剧集条目网址")
    # Only audited public image CDNs; no arbitrary visitor image host or signed/auth URL.
    if image and (host not in ("image.tmdb.org", "img1.doubanio.com", "img2.doubanio.com",
                              "img3.doubanio.com", "img9.doubanio.com") or p.query or p.fragment):
        raise ValueError("海报仅接受已审核的公开图片域名，且不能携带参数")
    return value


def public_image(value):
    try:
        return safe_url(value, image=True)
    except ValueError:
        return ""


def source_public_image(value, hosts=()):
    """Browser-only reference: explicitly audited exact hosts, never signed URLs."""
    try:
        value = safe_url(value)
        parsed = urlsplit(value)
        if (parsed.hostname or "").lower() not in hosts or parsed.query or parsed.fragment:
            return ""
        if not re.search(r"\.(?:jpe?g|png|webp|avif)$", parsed.path, re.IGNORECASE):
            return ""
        return value
    except (ValueError, TypeError):
        return ""


def rate_limit(db, key, limit=5, seconds=3600):
    if seconds <= 0 or limit < 1:
        return False
    window = int(time.time() // seconds)
    dialect = db.get_bind().dialect.name
    insert = sqlite_insert if dialect == "sqlite" else pg_insert if dialect == "postgresql" else None
    if insert is None:
        raise RuntimeError("限流仅支持 SQLite / PostgreSQL")
    # Concurrent first requests must not race a SELECT followed by INSERT.
    db.execute(insert(RateBucket).values(key=key, window=window, hits=0)
               .on_conflict_do_nothing(index_elements=[RateBucket.key]))
    db.execute(update(RateBucket).where(RateBucket.key == key, RateBucket.window < window)
               .values(window=window, hits=0))
    changed = db.execute(update(RateBucket).where(RateBucket.key == key, RateBucket.window == window,
                                                 RateBucket.hits < limit).values(hits=RateBucket.hits + 1))
    return changed.rowcount == 1


def parse_import(text):
    if len(text) > 100000:
        raise ValueError("每批文案最多 100000 字符")
    matches = list(re.finditer(
        r"https://(?:115\.com|115cdn\.com)/s/([A-Za-z0-9]+)(?![A-Za-z0-9/_%.-])"
        r"(?:[?#][^\s<>\"'，。；）)]*)?", text))
    if not matches:
        raise ValueError("未找到支持的 115 HTTPS 分享链接")
    if len(matches) > 100:
        raise ValueError("每批最多 100 条链接")
    if any(len(m[1]) > 120 or len(m.group()) > 2000 for m in matches):
        raise ValueError("分享码或链接过长")
    code_pattern = re.compile(r"(?:访问码|提取码|密码)\s*[:：]?\s*([A-Za-z0-9]{1,32})(?![A-Za-z0-9])")
    line_starts = [0] + [m.end() for m in re.finditer("\n", text)]
    from bisect import bisect_right
    def line_at(position):
        return bisect_right(line_starts, position) - 1
    blocks = [0] + [m.end() for m in re.finditer(r"\n[ \t]*\n", text)]
    codes = [[] for _ in matches]
    for code in code_pattern.finditer(text):
        if any(m.start() <= code.start() < m.end() for m in matches):
            continue
        block = bisect_right(blocks, code.start())
        candidates = [i for i, m in enumerate(matches) if bisect_right(blocks, m.start()) == block]
        if not candidates:
            continue
        line = line_at(code.start())
        same_line = [i for i in candidates if line_at(matches[i].start()) == line]
        if same_line:
            owner = min(same_line, key=lambda i: min(abs(code.start() - matches[i].end()),
                                                    abs(code.end() - matches[i].start())))
        else:
            end = text.find("\n", code.end())
            line_text = text[line_starts[line]:end if end >= 0 else len(text)]
            remainder = code_pattern.sub("", line_text).strip(" :：,，;；-—*#0123456789.、")
            following = [i for i in candidates if matches[i].start() > code.end()]
            # A labelled next-item line belongs to its following URL, not the previous package.
            if remainder and following and line_at(matches[following[0]].start()) == line + 1:
                owner = following[0]
            else:
                owner = min(candidates, key=lambda i: (abs(line_at(matches[i].start()) - line),
                                                       matches[i].start() > code.start()))
        codes[owner].append(code[1])
    output, seen = [], {}
    for i, m in enumerate(matches):
        url = m.group().rstrip("，。；,;）)\"'")
        values = parse_qs(urlsplit(url).query).get("password", []) + codes[i]
        values = list(dict.fromkeys(values))
        invalid = any(not re.fullmatch(r"[A-Za-z0-9]{1,32}", value) for value in values)
        conflict = len(values) > 1 or invalid
        line = line_at(m.start())
        prefix = code_pattern.sub("", text[line_starts[line]:m.start()]).strip(" :：,，;；")
        item = {"code": m[1], "url": url, "access_code": values[0] if values and not invalid else "",
                "title": prefix[:300] or m[1], "conflict": conflict, "warning": ""}
        if m[1] in seen:
            previous = seen[m[1]]
            different = bool(previous["access_code"] and item["access_code"]
                             and previous["access_code"] != item["access_code"])
            previous["conflict"] = previous["conflict"] or conflict or different
            previous["access_code"] = previous["access_code"] or item["access_code"]
            previous["warning"] = "重复分享访问码冲突，请人工确认" if previous["conflict"] else "重复分享已合并"
            continue
        item["warning"] = "访问码冲突或格式异常" if conflict else ("缺少访问码" if not values else "")
        output.append(item)
        seen[m[1]] = item
    return output
