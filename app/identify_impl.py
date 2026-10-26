from pathlib import PurePosixPath
import hashlib
import json
from sqlalchemy import func,or_,select
from .db import Node,Variant,Work
from .metadata_parse import SUBTITLE,parse_nfo,normalize_title
from .inference import infer
from .metadata_links import update_links,media_nodes
from .posters import observe_poster
def identify_directory(db,source,directory,readers,tmdb,media_node_id=None,local_only=False):
 if media_node_id is None:
  for n in db.scalars(media_nodes(source.id,directory)).all():identify_directory(db,source,directory,readers,tmdb,n.id,local_only)
  return
 node=db.scalar(media_nodes(source.id,directory).where(Node.id==media_node_id))
 if not node:return
 folder=db.scalar(select(Node).where(Node.source_id==source.id,Node.remote_id==str(directory)));chain=[];cur=folder;seen=set()
 while cur and cur.remote_id not in seen and len(chain)<100:seen.add(cur.remote_id);chain.append(cur);cur=db.scalar(select(Node).where(Node.source_id==source.id,Node.remote_id==cur.parent_remote_id))
 if any(x.name.upper()=="BDMV"for x in chain):return
 stem=PurePosixPath(node.name).stem.casefold();side=select(Node).where(Node.source_id==source.id,Node.parent_remote_id==str(directory),Node.is_dir.is_(False));nfos=db.scalars(side.where(or_(func.lower(Node.name)==stem+".nfo",func.lower(Node.name).in_(["movie.nfo","tvshow.nfo"]))).limit(8)).all();sel={};ep={}
 for n in ([] if local_only else nfos):
  try:v=parse_nfo(readers.nfo(source,n),readers.settings.nfo_limit,readers.settings.public_image_hosts)
  except Exception:v={}
  if v.get("nfo_kind")=="episodedetails":ep=v
  elif v.get("title")and not sel:sel=v
 nfo_poster=sel.get("poster","");external_poster=""
 g=infer(folder.name if node.is_dir and folder else node.name,folder.name if folder else"");title=sel.get("title")or ep.get("showtitle")or g["title"];year=sel.get("year")or g["year"];cat=sel.get("category")or("tv"if ep else g["category"]);info={k:v for k,v in sel.items()if k not in("title","year","category","stream","poster")};ext=info.get("external_ids",{})
 if title and not info.get("plot") and not local_only:
  m=tmdb.match(title,year,cat,ext)
  if m:
   external_poster=m.get("poster","")
   for k,v in m.items():
    if k not in("title","year","category","poster")and v and not info.get(k):info[k]=v
   year=year or m.get("year");ext=info.get("external_ids",ext)
 fallback=f"unconfirmed:{source.id}:{node.remote_id}"
 # Filename grouping is provisional, scoped to ONE source and directory. It
 # never merges names across sources or bypasses administrator confirmation.
 if local_only and title and (year or (cat=="tv" and g["season"] is not None)):
  key=json.dumps([source.id,str(directory),normalize_title(title),year,cat],ensure_ascii=False)
  fallback="local:"+hashlib.sha256(key.encode()).hexdigest()
 ident=next((f"{k}:{cat}:{ext[k]}"for k in("tmdb","imdb","fixture")if ext.get(k)and(k!="fixture"or source.adapter=="mock")),fallback);var=db.scalar(select(Variant).where(Variant.node_id==node.id));work=db.get(Work,var.work_id)if var else db.scalar(select(Work).where(Work.identity==ident));info["collection_links"]=[[x.name,"source"]for x in chain if"合集"in x.name]
 if not work:work=Work(identity=ident,title=title or"未识别资源",year=year,category=cat,status="confirmed"if ext and year and info.get("plot")else"review",visible=bool(title),info=info,provenance={k:"NFO"for k in info},locked=[]);db.add(work);db.flush()
 else:
  merged=dict(work.info)
  for k,v in info.items():
   if v and k not in work.locked and not merged.get(k):merged[k]=v
  work.info=merged
 if local_only:
  work.provenance=dict(work.provenance,identification="仅已索引文件名推断；未经 NFO/TMDB 校验")
 if not local_only:observe_poster(work,"nfo",nfo_poster,readers.settings.public_image_hosts,source.id,node.id)
 if external_poster:observe_poster(work,"external",external_poster,readers.settings.public_image_hosts,source.id,node.id)
 update_links(db,work);a=dict(g["attributes"]);a.update(sel.get("stream",{}));a.update(ep.get("stream",{}))
 if ep:a["episode_title"]=ep.get("title","");g["season"]=ep.get("season",g["season"]);g["episodes"]=[ep["episode"]]if ep.get("episode")is not None else g["episodes"]
 subs=db.scalars(side.where(or_(*[func.lower(Node.name).endswith(x)for x in SUBTITLE]),func.lower(Node.name).contains(stem)).limit(100)).all()
 if subs:a["subtitle"],a["subtitle_files"]="外挂字幕",[x.path for x in subs]
 if node.is_dir:a["format"]="BDMV"
 a["original_disc"]=a.get("format")in("ISO","BDMV")
 if var:var.attributes,var.season,var.episodes=a,g["season"],g["episodes"]
 else:db.add(Variant(work_id=work.id,source_id=source.id,node_id=node.id,attributes=a,season=g["season"],episodes=g["episodes"],resource_group=folder.name if folder else""))
