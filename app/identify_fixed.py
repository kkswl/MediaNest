from sqlalchemy import select
from .db import Collection,Node,Variant,Work,WorkCollection
from .identify_impl import identify_directory as base_identify
from .metadata_links import update_links
from .security import source_public_image
def identify_directory(db,source,directory,readers,tmdb,media_node_id=None):
 base_identify(db,source,directory,readers,tmdb,media_node_id)
 if media_node_id is None:return
 node=db.get(Node,media_node_id); variant=db.scalar(select(Variant).where(Variant.node_id==media_node_id))
 if not node or not variant:return
 work=db.get(Work,variant.work_id); info=dict(work.info)
 links=list(info.get("collection_links",[])); collection=info.get("collection")
 if collection and [collection,"series"] not in links:links.append([collection,"series"])
 if links:info["collection_links"]=links
 if not info.get("poster"):
  poster=db.scalar(select(Node).where(Node.source_id==source.id,Node.parent_remote_id==node.parent_remote_id,Node.name.ilike("%poster.%")))
  address=source_public_image(poster.public_image,readers.settings.public_image_hosts) if poster else ""
  if address:info["poster"]=address
 if info!=work.info:work.info=info;update_links(db,work)
