"""Poster evidence and browser-only URL selection; never fetch image content."""

from pathlib import PurePosixPath

from sqlalchemy import select

from .db import Node
from .inference import infer
from .metadata_links import media_nodes
from .metadata_parse import normalize_title
from .security import public_image, source_public_image

PRIORITY = {"nfo": 0, "directory": 1, "external": 2, "legacy_unknown": 3}


def image_url(value, hosts=()):
    if not isinstance(value, str):
        return ""
    return public_image(value) or source_public_image(value, hosts)


def select_poster(info, locked=(), hosts=()):
    """Conservative lazy migration: an unmarked legacy URL is not a manual lock."""
    result = dict(info or {})
    candidates = []
    for item in result.get("poster_candidates", []) or []:
        if not isinstance(item, dict) or item.get("kind") not in PRIORITY:
            continue
        url = image_url(item.get("url"), hosts)
        if url:
            candidate = {k: item[k] for k in ("kind", "source_id", "node_id") if k in item}
            candidate["url"] = url
            if candidate not in candidates:
                candidates.append(candidate)
    legacy = image_url(result.get("poster"), hosts)
    if legacy and not result.get("poster_source") and "poster" not in locked:
        candidate = {"kind": "legacy_unknown", "url": legacy}
        if candidate not in candidates:
            candidates.append(candidate)
    for key in ("fallback_poster", "tmdb_poster"):
        url = public_image(result.get(key, "")) if isinstance(result.get(key, ""), str) else ""
        if url and not any(c["url"] == url for c in candidates):
            candidates.append({"kind": "external", "url": url})
    candidates.sort(key=lambda c: PRIORITY[c["kind"]])
    candidates = candidates[:64]
    manual = "poster" in locked
    chosen = {"url": legacy, "kind": "manual"} if manual else (candidates[0] if candidates else {})
    fallback = next((c for c in candidates if c["url"] != chosen.get("url") and (
        c["kind"] == "external" or (c["kind"] == "legacy_unknown" and public_image(c["url"])))), {})
    result.update(poster=chosen.get("url", ""), poster_source=chosen.get("kind", "placeholder"),
                  poster_locked=manual, poster_candidates=candidates,
                  fallback_poster=fallback.get("url", ""), fallback_poster_source=fallback.get("kind", ""))
    # Legacy frontend aliases must not bypass the same URL policy.
    for key in ("poster_public_url", "poster_url", "tmdb_poster"):
        if key in result:
            result[key] = image_url(result[key], hosts)
    return result


def observe_poster(work, kind, value, hosts, source_id=None, node_id=None):
    info = select_poster(work.info, work.locked, hosts)
    candidates = [c for c in info["poster_candidates"] if not (
        c["kind"] == kind and c.get("source_id") == source_id and c.get("node_id") == node_id)]
    url = image_url(value, hosts)
    if url:
        candidates.append({"kind": kind, "url": url, "source_id": source_id, "node_id": node_id})
    info["poster_candidates"] = candidates
    work.info = select_poster(info, work.locked, hosts)


def directory_poster(db, source, node, work):
    siblings = db.scalars(select(Node).where(Node.source_id == source.id,
                                           Node.parent_remote_id == node.parent_remote_id,
                                           Node.is_dir.is_(False)).order_by(Node.id)).all()
    media = db.scalars(media_nodes(source.id, node.parent_remote_id)).all()
    inferred = [infer(item.name, "") for item in media]
    same_title_years = {p.get("year") for p in inferred
                        if normalize_title(p.get("title") or "") == normalize_title(work.title)}
    stems = {PurePosixPath(node.name).stem.casefold()}
    if len(same_title_years) <= 1:
        stems.add(work.title.casefold())
    exact = {stem + suffix for stem in stems for suffix in ("-poster", ".poster", "-folder")}
    matches = [n for n in siblings if PurePosixPath(n.name).stem.casefold() in exact
               and PurePosixPath(n.name).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".avif")]
    if matches:
        return matches
    # Generic poster.jpg/folder.jpg is safe only for a single identifiable work,
    # including multiple encodes of it. Never arbitrarily bind a shared folder.
    single_disc = len(media) == 1 and media[0].is_dir and media[0].name.upper() == "BDMV"
    identities = set()
    for item, parsed in zip(media, inferred, strict=True):
        title = normalize_title(parsed.get("title") or "")
        if single_disc:
            identities.add(("single-disc", None))
            continue
        if not title or item.is_dir:
            return []
        identities.add((title, parsed.get("year")))
    if len(identities) != 1:
        return []
    return [n for n in siblings if n.name.casefold() in (
        "poster.jpg", "poster.png", "poster.webp", "folder.jpg", "folder.png")]
