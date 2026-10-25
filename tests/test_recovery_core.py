import pytest
from defusedxml.common import DefusedXmlException
from sqlalchemy import func, select

from app.db import Node, Task, Variant, Work
from app.metadata import infer, normalize_title, parse_nfo


def test_nfo_and_filename_metadata_are_structured():
    value = parse_nfo(b'<movie><title>Demo</title><year>2024</year><uniqueid type="tmdb">42</uniqueid><genre>Drama</genre><fileinfo><streamdetails><audio><language>zho</language></audio><video><height>2160</height></video></streamdetails></fileinfo></movie>')
    assert value["title"] == "Demo"
    assert value["external_ids"] == {"tmdb": "42"}
    assert value["stream"]["resolution"] == "4K"
    assert infer("Demo.2024.2160p.国语.iso")["attributes"]["format"] == "ISO"
    assert normalize_title("ＡＢＣ：2024") == normalize_title("abc2024")


def test_nfo_entity_and_untrusted_image_rejected():
    with pytest.raises(DefusedXmlException):
        parse_nfo(b'<!DOCTYPE movie [<!ENTITY x SYSTEM "file:///secret">]><movie><title>&x;</title></movie>')
    assert parse_nfo(b'<movie><title>x</title><thumb>https://127.0.0.1/x.jpg</thumb></movie>')["poster"] == ""


def test_synthetic_worker_indexes_versions_and_keeps_disc_contents_out(environment):
    database, _, _, worker, _ids = environment
    assert worker.drain() > 0
    with database.session() as db:
        assert db.get(Work, db.scalar(select(Work.id).where(Work.title == "星海来信")))
        work = db.scalar(select(Work).where(Work.title == "星海来信"))
        formats = {x.attributes.get("format") for x in db.scalars(select(Variant).where(Variant.work_id == work.id)).all()}
        assert {"MKV", "ISO", "BDMV"}.issubset(formats)
        stream = db.scalar(select(Node).where(Node.name == "00001.m2ts"))
        assert stream is not None and db.scalar(select(Variant).where(Variant.node_id == stream.id)) is None
        assert db.scalar(select(func.count()).select_from(Task).where(Task.status == "failed")) == 0
