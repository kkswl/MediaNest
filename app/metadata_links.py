from sqlalchemy import func,or_,select
from .db import Collection,Node,Person,WorkCollection,WorkPerson
from .metadata_parse import VIDEO
def update_links(db,work):
 wanted=set(work.info.get("actors",[]))
 for link in db.scalars(select(WorkPerson).where(WorkPerson.work_id==work.id)).all():
  p=db.get(Person,link.person_id)
  if p and p.name not in wanted:db.delete(link)
 for name in wanted:
  p=db.scalar(select(Person).where(Person.name==name))
  if not p:p=Person(name=name[:300]);db.add(p);db.flush()
  if not db.get(WorkPerson,(work.id,p.id)):db.add(WorkPerson(work_id=work.id,person_id=p.id))
 for name,kind in work.info.get("collection_links",[]):
  c=db.scalar(select(Collection).where(Collection.name==name,Collection.kind==kind))
  if not c:c=Collection(name=name[:500],kind=kind);db.add(c);db.flush()
  if not db.get(WorkCollection,(work.id,c.id)):db.add(WorkCollection(work_id=work.id,collection_id=c.id))
def media_nodes(source_id,directory):
 s=[func.lower(Node.name).endswith(x)for x in VIDEO]
 return select(Node).where(Node.source_id==source_id,Node.parent_remote_id==str(directory),or_(Node.is_dir.is_(True)&(func.upper(Node.name)=="BDMV"),Node.is_dir.is_(False)&or_(*s)))
