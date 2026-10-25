from sqlalchemy import select
from .db import Node,Variant,Work
from .identify_impl import identify_directory as base
from .metadata_links import media_nodes,update_links
from .security import source_public_image
def identify_directory(db,source,directory,readers,tmdb,media_node_id=None):
 if media_node_id is None:
  base(db,source,directory,readers,tmdb,None)
  ids=[n.id for n in db.scalars(media_nodes(source.id,directory)).all()]
  for ident in ids:identify_directory(db,source,directory,readers,tmdb,ident)
  return
 base(db,source,directory,readers,tmdb,media_node_id)
 node=db.get(Node,media_node_id);var=db.scalar(select(Variant).where(Variant.node_id==media_node_id))
 if not node or not var:return
 work=db.get(Work,var.work_id);info=dict(work.info);links=list(info.get("collection_links",[]));c=info.get("collection")
 if c and [c,"series"] not in links:links.append([c,"series"])
 if links:info["collection_links"]=links
 if not info.get("poster"):
  p=db.scalar(select(Node).where(Node.source_id==source.id,Node.parent_remote_id==node.parent_remote_id,Node.name.ilike("%poster.%")))
  address=source_public_image(p.public_image,readers.settings.public_image_hosts) if p else ""
  if address:info["poster"]=address
 if info!=work.info:work.info=info;update_links(db,work)
