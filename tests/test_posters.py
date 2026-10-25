import pytest
from sqlalchemy import select

from app.db import Node, Source, Variant, Work
from app.metadata import identify_directory
from app.posters import directory_poster, observe_poster, select_poster

HOSTS = ("posters.synthetic.example",)
SOURCE = "https://posters.synthetic.example/poster.jpg"
EXTERNAL = "https://image.tmdb.org/t/p/w500/synthetic.jpg"
MANUAL = "https://image.tmdb.org/t/p/w500/manual.jpg"


def work(info=None, locked=None):
    return Work(info=info or {}, locked=locked or [])


def test_evidence_priority_and_external_fallback():
    item = work({"poster": EXTERNAL})
    observe_poster(item, "external", EXTERNAL, HOSTS)
    observe_poster(item, "directory", SOURCE, HOSTS, 1, 1)
    assert item.info["poster"] == SOURCE
    assert item.info["poster_source"] == "directory"
    assert item.info["fallback_poster"] == EXTERNAL
    nfo = "https://posters.synthetic.example/nfo.jpg"
    observe_poster(item, "nfo", nfo, HOSTS, 1, 1)
    assert item.info["poster"] == nfo and item.info["poster_source"] == "nfo"
    observe_poster(item, "directory", SOURCE, HOSTS, 1, 1)
    assert item.info["poster"] == nfo
    item.info = dict(item.info, poster=MANUAL)
    item.locked = ["poster"]
    observe_poster(item, "nfo", SOURCE, HOSTS, 1, 1)
    assert item.info["poster"] == MANUAL and item.info["poster_locked"]
    assert item.info["poster_source"] == "manual"


@pytest.mark.parametrize("url", ["http://posters.synthetic.example/a.jpg", "https://evil.example/a.jpg",
    "https://127.0.0.1/a.jpg", "https://192.168.1.1/a.jpg", "https://localhost/a.jpg",
    "https://image.tmdb.org/a.jpg?token=secret", "https://posters.synthetic.example/a.jpg?password=secret",
    "https://user:secret@image.tmdb.org/a.jpg", "https://image.tmdb.org/a.jpg#token=secret"])
def test_all_candidate_and_legacy_urls_are_scrubbed(url):
    info = select_poster({"poster": url, "poster_public_url": url, "poster_url": url, "tmdb_poster": url,
                          "fallback_poster": url, "poster_candidates": [{"kind": "nfo", "url": url}]}, [], HOSTS)
    assert info["poster"] == info["fallback_poster"] == ""
    assert info["poster_candidates"] == []
    assert url not in str(info)


def test_legacy_is_not_manual_and_external_works_without_source():
    info = select_poster({"poster": EXTERNAL}, [], HOSTS)
    assert info["poster"] == EXTERNAL and info["poster_source"] == "legacy_unknown"
    assert not info["poster_locked"]
    legacy = work({"poster": EXTERNAL})
    observe_poster(legacy, "directory", SOURCE, HOSTS, 1, 1)
    assert legacy.info["fallback_poster"] == EXTERNAL
    assert legacy.info["fallback_poster_source"] == "legacy_unknown"
    item = work({"fallback_poster": EXTERNAL})
    observe_poster(item, "nfo", "https://evil.example/a.jpg", HOSTS)
    assert item.info["poster"] == EXTERNAL and item.info["poster_source"] == "external"


def test_identify_replaces_external_and_preserves_admin_lock(api):
    app, owner, _other, public, ids = api
    app.state.settings.public_image_hosts = HOSTS
    with app.state.database.session.begin() as db:
        poster = db.scalar(select(Node).where(Node.name == "星海来信-poster.jpg"))
        poster.public_image = SOURCE
        variant = db.scalar(select(Variant).join(Node).where(Node.parent_remote_id == poster.parent_remote_id))
        item = db.get(Work, variant.work_id)
        item.info = dict(item.info, poster=EXTERNAL, fallback_poster=EXTERNAL)
        identify_directory(db, db.get(Source, ids["source"]), poster.parent_remote_id,
                           app.state.readers, app.state.worker.tmdb)
        wid, directory = item.id, poster.parent_remote_id
    assert public.get(f"/api/works/{wid}").json()["info"]["poster"] == SOURCE
    assert owner.patch(f"/api/admin/works/{wid}", json={"poster": MANUAL}).status_code == 200
    with app.state.database.session.begin() as db:
        identify_directory(db, db.get(Source, ids["source"]), directory, app.state.readers, app.state.worker.tmdb)
    info = public.get(f"/api/works/{wid}").json()["info"]
    assert info["poster"] == MANUAL and info["poster_locked"] and info["poster_source"] == "manual"


def test_generic_poster_not_shared_by_different_movies(environment):
    database, _settings, _readers, _worker, ids = environment
    with database.session.begin() as db:
        source = db.get(Source, ids["source"])
        first = Node(source_id=source.id, remote_id="film1", parent_remote_id="0",
                     name="Alpha.2024.mkv", path="Alpha.2024.mkv", is_dir=False)
        second = Node(source_id=source.id, remote_id="film2", parent_remote_id="0",
                      name="Beta.2025.mkv", path="Beta.2025.mkv", is_dir=False)
        poster = Node(source_id=source.id, remote_id="poster", parent_remote_id="0", name="poster.jpg",
                      path="poster.jpg", is_dir=False, public_image=SOURCE)
        db.add_all([first, second, poster])
        db.flush()
        assert directory_poster(db, source, first, Work(title="Alpha")) == []
        assert directory_poster(db, source, second, Work(title="Beta")) == []
        poster.name = "Alpha-poster.jpg"
        db.flush()
        assert directory_poster(db, source, first, Work(title="Alpha")) == [poster]
        assert directory_poster(db, source, second, Work(title="Beta")) == []


def test_nfo_poster_evidence_from_active_identification(environment, monkeypatch):
    database, settings, readers, worker, ids = environment
    settings.public_image_hosts = HOSTS
    original = readers.mock.read_nfo
    def nfo(*args, **kwargs):
        data = original(*args, **kwargs)
        return data.replace(b"</movie>", (f"<thumb>{SOURCE}</thumb></movie>").encode())
    monkeypatch.setattr(readers.mock, "read_nfo", nfo)
    worker.drain()
    with database.session.begin() as db:
        poster = db.scalar(select(Node).where(Node.name == "星海来信-poster.jpg"))
        poster.public_image = "https://posters.synthetic.example/directory.jpg"
        identify_directory(db, db.get(Source, ids["source"]), poster.parent_remote_id, readers, worker.tmdb)
        item = db.scalar(select(Work).where(Work.title == "星海来信"))
        assert item.info["poster"] == SOURCE and item.info["poster_source"] == "nfo"


def test_same_title_remakes_do_not_share_unqualified_poster(environment):
    database, _settings, _readers, _worker, ids = environment
    with database.session.begin() as db:
        source = db.get(Source, ids["source"])
        films = [Node(source_id=source.id, remote_id=str(year), parent_remote_id="0", name=f"Alpha.{year}.mkv",
                      path=f"Alpha.{year}.mkv", is_dir=False) for year in (2000, 2024)]
        poster = Node(source_id=source.id, remote_id="poster", parent_remote_id="0", name="Alpha-poster.jpg",
                      path="Alpha-poster.jpg", is_dir=False, public_image=SOURCE)
        db.add_all([*films, poster])
        db.flush()
        for film in films:
            assert directory_poster(db, source, film, Work(title="Alpha")) == []
        poster.name = "Alpha.2024-poster.jpg"
        db.flush()
        assert directory_poster(db, source, films[1], Work(title="Alpha")) == [poster]
        assert directory_poster(db, source, films[0], Work(title="Alpha")) == []
