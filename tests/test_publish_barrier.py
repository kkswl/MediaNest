from sqlalchemy import select

from app.db import Collection, Node, Person, Source, Variant, Work, WorkCollection, WorkPerson


def test_review_barrier_all_public_endpoints_and_reversible_approval(api):
    app, owner, _other, public, ids = api
    with app.state.database.session.begin() as db:
        work = Work(identity="fixture:private", title="仅后台可见的模拟作品", year=2026,
                    status="review", visible=True, info={"actors": ["仅后台模拟演员"],
                        "collection_links": [["仅后台模拟合集", "series"]]}, provenance={}, locked=[])
        person = Person(name="仅后台模拟演员")
        collection = Collection(name="仅后台模拟合集", kind="series")
        source = Source(owner_id=ids["admin"], code="privatefixture", url="https://115.com/s/demoa",
                        title="仅后台来源", adapter="mock")
        db.add_all([work, person, collection, source])
        db.flush()
        node = Node(source_id=source.id, remote_id="private", parent_remote_id="0", name="私有.mkv",
                    path="私有.mkv", is_dir=False)
        db.add(node)
        db.flush()
        db.add_all([Variant(work_id=work.id, source_id=source.id, node_id=node.id),
                    WorkPerson(work_id=work.id, person_id=person.id),
                    WorkCollection(work_id=work.id, collection_id=collection.id)])
        wid, pid, cid = work.id, person.id, collection.id

    initial = public.get("/api/stats").json()
    assert initial["review"] == 0

    def assert_private():
        assert public.get(f"/api/works/{wid}").status_code == 404
        for params in ({}, {"q": "仅后台"}, {"person": pid}, {"collection": cid}):
            assert wid not in [w["id"] for w in public.get("/api/catalog", params=params).json()["items"]]
        assert pid not in [p["id"] for p in public.get("/api/people").json()["items"]]
        assert cid not in [c["id"] for c in public.get("/api/collections").json()["items"]]
        assert public.get("/api/stats").json() == initial
        assert public.post("/api/suggestions", json={"work_id": wid, "changes": {"title": "无权建议"}}).status_code == 404

    assert_private()
    assert wid in [w["id"] for w in owner.get("/api/admin/review").json()["items"]]
    assert owner.patch(f"/api/admin/works/{wid}", json={"status": "confirmed"}).status_code == 200
    assert public.get(f"/api/works/{wid}").status_code == 200
    counts = public.get("/api/stats").json()
    assert counts["works"] == initial["works"] + 1
    assert counts["variants"] == initial["variants"] + 1
    assert counts["sources"] == initial["sources"] + 1
    assert pid in [p["id"] for p in public.get("/api/people").json()["items"]]
    assert cid in [c["id"] for c in public.get("/api/collections").json()["items"]]
    assert owner.patch(f"/api/admin/works/{wid}", json={"status": "review"}).status_code == 200
    assert_private()
    assert owner.patch(f"/api/admin/works/{wid}", json={"status": "confirmed", "visible": False}).status_code == 200
    assert_private()
    with app.state.database.session() as db:
        assert db.get(Work, wid) is not None
        assert db.scalar(select(Variant).where(Variant.work_id == wid)) is not None
