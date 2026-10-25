from types import SimpleNamespace

import pytest

from app.adapters import MockReader, P115Reader, ReadError
from app.config import Settings
from app.fixtures import directory_fixture


def test_fixture_is_synthetic_and_contains_required_categories():
    tree, contents = directory_fixture("demoa")
    names = [x["name"] for page in tree.values() for x in page]
    assert "林舟作品合集" in names
    assert "星海系列合集" in names
    assert "BDMV" in names
    assert any(x.endswith(".iso") for x in names)
    assert any("S01E04" in x for x in names)
    assert any(x.endswith(".srt") for x in names)
    assert any(x.endswith("-poster.jpg") for x in names)
    combined = b"\n".join(contents.values())
    assert all(f"<category>{category}</category>".encode() in combined
               for category in ("movie", "tv", "anime", "variety", "concert"))
    for parent, children in tree.items():
        assert all(node["parent"] == parent for node in children)
    assert directory_fixture("unsupported-synthetic")[0] == {"0": []}


def test_mock_reader_pagination_preserves_every_node():
    source = SimpleNamespace(code="demoa")
    reader = MockReader()
    expected, _ = directory_fixture(source.code)
    for directory, items in expected.items():
        result, offset = [], 0
        while True:
            page, total = reader.list_page(source, directory, offset, 2)
            result.extend(page)
            offset += len(page)
            if offset >= total:
                break
            assert page, "pagination must advance"
        assert result == items
    assert len(reader.calls) > len(expected)


def test_mock_reader_injected_timeout_is_not_missing():
    source = SimpleNamespace(code="demoa")
    reader = MockReader()
    reader.faults[("demoa", "0", 0)] = ["timeout"]
    with pytest.raises(ReadError) as caught:
        reader.list_page(source, "0", 0, 2)
    assert caught.value.kind == "timeout"
    assert reader.list_page(source, "0", 0, 2)[0]
    reader.missing.add(("demoa", "0"))
    with pytest.raises(ReadError) as caught:
        reader.list_page(source, "0", 0, 2)
    assert caught.value.kind == "missing"


def test_nfo_is_bytes_and_size_limited():
    source = SimpleNamespace(code="demoa")
    _, contents = directory_fixture("demoa")
    node = SimpleNamespace(remote_id=next(iter(contents)))
    reader = MockReader()
    assert reader.read_nfo(source, node, 262144).startswith(b"<movie>")
    with pytest.raises(ReadError) as caught:
        reader.read_nfo(source, node, 2)
    assert caught.value.kind == "oversize"


def test_live_reader_disabled_before_client_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("disabled live adapter must not reach network")
    monkeypatch.setattr("httpx.stream", forbidden)
    reader = P115Reader(Settings(secret="x" * 40, live_enabled=False))
    with pytest.raises(ReadError) as caught:
        reader.client("synthetic-cookie")
    assert caught.value.kind == "disabled"


def test_live_unknown_response_is_never_missing():
    reader = P115Reader(Settings(secret="x" * 40))
    for response in (None, [], {"state": False, "errno": 999999}):
        with pytest.raises(ReadError) as caught:
            reader.response(response)
        assert caught.value.kind in ("uncertain", "unknown")


@pytest.mark.parametrize("data", [
    {"list": [], "count": 2},
    {"list": [], "count": -1},
    {"list": [{"fid": "1", "cid": "0", "n": "file.mkv", "s": -1}], "count": 1},
    {"list": [{"fid": "1", "cid": "other-parent", "n": "file.mkv", "s": 1}], "count": 1},
    {"list": [{"fid": "1", "cid": "0", "n": "../file.mkv", "s": 1}], "count": 1},
    {"list": [{"fid": "1", "cid": "0", "n": "file.mkv", "s": 1}] * 2, "count": 2},
])
def test_live_pagination_malformed_never_proves_absence(monkeypatch, data):
    reader = P115Reader(Settings(secret="x" * 40, live_enabled=True))
    client = SimpleNamespace(share_snap=lambda *args, **kwargs: {"state": True, "data": data})
    monkeypatch.setattr(reader, "client", lambda cookie: client)
    monkeypatch.setattr(reader, "throttle", lambda: None)
    source = SimpleNamespace(code="synthetic", access_code="aaaa")
    with pytest.raises(ReadError) as caught:
        reader.list_page(source, "0", 0, 2, "synthetic")
    assert caught.value.kind == "uncertain"


def test_live_response_distinguishes_explicit_missing_and_auth():
    reader = P115Reader(Settings(secret="x" * 40))
    for text, expected in (("分享已取消", "missing"), ("登录失效", "auth"),
                           ("访问码错误", "locked"), ("操作频繁", "rate_limited"),
                           ("发生了未知错误", "uncertain")):
        with pytest.raises(ReadError) as caught:
            reader.response({"state": False, "error": text})
        assert caught.value.kind == expected
