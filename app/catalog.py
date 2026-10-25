from sqlalchemy import String, func, or_, select

from .db import Collection, Node, Person, Source, Variant, Work, WorkCollection, WorkPerson
from .health import effective_health
from .posters import select_poster


def valid_variants():
    blocked = select(Node.id.label("id"), Node.source_id.label("source_id"),
                     Node.remote_id.label("remote_id")).where(Node.health == "missing").cte(recursive=True)
    blocked = blocked.union(select(Node.id, Node.source_id, Node.remote_id).join(
        blocked, (Node.source_id == blocked.c.source_id) & (Node.parent_remote_id == blocked.c.remote_id)))
    return select(Variant).join(Source, Source.id == Variant.source_id).join(Node, Node.id == Variant.node_id).where(
        Source.enabled.is_(True), Source.health != "missing", ~Node.id.in_(select(blocked.c.id)))


def public_works():
    available = valid_variants().with_only_columns(Variant.work_id)
    return select(Work).where(Work.status == "confirmed", Work.visible.is_(True), Work.id.in_(available))


def work_dict(db, work, image_hosts=()):
    info = select_poster(work.info, work.locked, image_hosts)
    people = [{"id": p.id, "name": p.name} for p in db.scalars(select(Person).join(WorkPerson).where(
        WorkPerson.work_id == work.id)).all()]
    collections = [{"id": c.id, "name": c.name, "kind": c.kind} for c in db.scalars(
        select(Collection).join(WorkCollection).where(WorkCollection.work_id == work.id)).all()]
    return {"id": work.id, "title": work.title, "year": work.year, "category": work.category,
            "status": work.status, "visible": work.visible, "info": info, "provenance": work.provenance,
            "people": people, "collections": collections,
            "variant_count": db.scalar(select(func.count()).select_from(valid_variants().where(
                Variant.work_id == work.id).subquery()))}


def variant_dict(db, variant, work):
    source, node = db.get(Source, variant.source_id), db.get(Node, variant.node_id)
    override = work.info.get("path_overrides", {}).get(str(variant.id), "")
    return {"id": variant.id, "source_id": source.id, "node_id": node.id, "name": node.name,
            "path": override or node.path, "original_path": node.path, "path_corrected": bool(override),
            "size": node.size, "share_url": source.url, "access_code": source.access_code,
            "source_title": source.title, "source_access_status": source.access_status,
            "health": effective_health(db, source, node),
            "checked_at": node.checked_at, "attributes": variant.attributes, "season": variant.season,
            "episodes": variant.episodes, "resource_group": variant.resource_group}


def catalog_query(q="", category="", year=None, resolution="", language="", subtitle="", format="",
                  person=None, collection=None, genre=""):
    query = public_works()
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = "%" + escaped + "%"
        query = query.where(or_(Work.title.ilike(pattern, escape="\\"),
                                Work.info["original_title"].as_string().ilike(pattern, escape="\\"),
                                Work.info["aliases"].cast(String).ilike(pattern, escape="\\"),
                                Work.info["genres"].cast(String).ilike(pattern, escape="\\"),
                                Work.id.in_(valid_variants().with_only_columns(Variant.work_id).where(
                                    or_(Node.path.ilike(pattern, escape="\\"),
                                        Node.name.ilike(pattern, escape="\\"),
                                        Variant.attributes.cast(String).ilike(pattern, escape="\\")))),
                                Work.id.in_(select(WorkPerson.work_id).join(Person).where(
                                    Person.name.ilike(pattern, escape="\\"))),
                                Work.id.in_(select(WorkCollection.work_id).join(Collection).where(
                                    Collection.name.ilike(pattern, escape="\\")))))
    if category:
        query = query.where(Work.category == category)
    if year:
        query = query.where(Work.year == year)
    if genre:
        query = query.where(Work.info["genres"].cast(String).contains(genre, autoescape=True))
    if person:
        query = query.where(Work.id.in_(select(WorkPerson.work_id).where(WorkPerson.person_id == person)))
    if collection:
        query = query.where(Work.id.in_(select(WorkCollection.work_id).where(WorkCollection.collection_id == collection)))
    filters = {"resolution": resolution, "language": language, "subtitle": subtitle, "format": format}
    vquery = valid_variants().with_only_columns(Variant.work_id)
    has_filter = False
    for field, value in filters.items():
        if value:
            vquery = vquery.where(Variant.attributes[field].as_string() == value)
            has_filter = True
    if has_filter:
        query = query.where(Work.id.in_(vquery))
    return query
