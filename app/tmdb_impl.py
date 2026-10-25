import re,httpx
from .metadata_parse import normalize_title
class TMDB:
 def __init__(self,settings):self.settings=settings
 def match(self,title,year,category,external_ids=None):
  if not self.settings.tmdb_token or not getattr(self.settings,"tmdb_enabled",False):return None
  ids=external_ids or {};media="tv"if category in("tv","anime","variety")else"movie"
  try:
   ident=str(ids.get("tmdb", ""))
   if ident and not re.fullmatch(r"\d+",ident):return None
   if not ident:
    r=httpx.get(f"https://api.themoviedb.org/3/search/{media}",params={"query":title,"language":"zh-CN","first_air_date_year"if media=="tv"else"year":year},headers={"Authorization":"Bearer "+self.settings.tmdb_token},timeout=10);r.raise_for_status();h=[]
    for x in r.json().get("results",[]):
     n=[x.get(k,"")for k in("title","original_title","name","original_name")];d=x.get("release_date")or x.get("first_air_date")or""
     if normalize_title(title) in[normalize_title(z)for z in n]and year and d[:4]==str(year):h.append(x)
    if len(h)!=1:return None
    ident=str(h[0]["id"])
   r=httpx.get(f"https://api.themoviedb.org/3/{media}/{ident}",params={"language":"zh-CN","append_to_response":"credits,external_ids"},headers={"Authorization":"Bearer "+self.settings.tmdb_token},timeout=10);r.raise_for_status();d=r.json();date=d.get("release_date")or d.get("first_air_date")or""
   if str(d.get("id"))!=ident:return None
   return{"title":d.get("title")or d.get("name"),"year":int(date[:4])if date[:4].isdigit()else year,"category":category,"external_ids":{**ids,"tmdb":ident},"plot":d.get("overview",""),"genres":[x["name"]for x in d.get("genres",[])],"actors":[x["name"]for x in d.get("credits",{}).get("cast",[])[:30]],"fallback_poster":"https://image.tmdb.org/t/p/w500"+d["poster_path"]if d.get("poster_path")else""}
  except(httpx.HTTPError,ValueError,KeyError,TypeError):return None
