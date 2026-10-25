from sqlalchemy import select
from .db import Node,Variant,Work
from .identify_impl import identify_directory as base
from .metadata_links import media_nodes,update_links
from .posters import directory_poster,image_url,observe_poster
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
 if info!=work.info:work.info=info;update_links(db,work)
 candidates=directory_poster(db,source,node,work)
 poster=next((p for p in candidates if image_url(p.public_image,readers.settings.public_image_hosts)),None)
 observe_poster(work,"directory",poster.public_image if poster else "",readers.settings.public_image_hosts,source.id,node.id)
