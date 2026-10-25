import re,unicodedata
from pathlib import PurePosixPath
from defusedxml import ElementTree
from guessit import guessit
from .security import public_image,source_public_image
CATEGORIES={"movie","tv","variety","anime","concert"};VIDEO={".mkv",".mp4",".avi",".mov",".ts",".iso",".m4v",".wmv"};SUBTITLE={".srt",".ass",".ssa",".sub",".sup",".vtt"}
def txt(n,p,d=""):return(n.findtext(p)or d).strip()[:10000]
def parse_nfo(data,limit=262144,image_hosts=()):
 if len(data)>limit:raise ValueError("NFO 超出大小上限")
 root=ElementTree.fromstring(data,forbid_dtd=True,forbid_entities=True,forbid_external=True)
 if root.tag not in("movie","tvshow","episodedetails","musicvideo"):raise ValueError("不支持的 NFO 根节点")
 y=re.search(r"\b(19\d{2}|20\d{2})\b",txt(root,"year")or txt(root,"premiered"));cat=txt(root,"category")or("tv"if root.tag in("tvshow","episodedetails")else"concert"if root.tag=="musicvideo"else"movie")
 o={"title":txt(root,"title"),"original_title":txt(root,"originaltitle"),"year":int(y[1])if y else None,"plot":txt(root,"plot"),"genres":[(x.text or"").strip()for x in root.findall("genre")if x.text],"actors":[txt(x,"name")for x in root.findall("actor")if txt(x,"name")],"collection":txt(root,"set/name")or txt(root,"set"),"poster":public_image(txt(root,"thumb"))or source_public_image(txt(root,"thumb"),image_hosts),"showtitle":txt(root,"showtitle"),"category":cat if cat in CATEGORIES else"movie","nfo_kind":root.tag,"external_ids":{}}
 for x in root.findall("uniqueid"):
  t=x.attrib.get("type","").lower();v=(x.text or"").strip()[:100];p=r"tt\d+"if t=="imdb"else r"\d+"if t in("tmdb","douban")else r"[\w.-]+"
  if t in("tmdb","imdb","douban","fixture")and re.fullmatch(p,v):o["external_ids"][t]=v
 for k in("season","episode"):
  v=txt(root,k)
  if v.isdigit():o[k]=int(v)
 s=root.find("fileinfo/streamdetails");a={}
 if s is not None:
  ls=[txt(x,"language")for x in s.findall("audio")if txt(x,"language")];ss=[txt(x,"language")for x in s.findall("subtitle")if txt(x,"language")]
  if ls:a["audio_languages"]=ls;a["language"]="国语"if any(x.lower()in("zho","chi","zh","cmn")for x in ls)else"未知"
  if ss:a["subtitle"],a["subtitle_languages"]="内封字幕",ss
  h=txt(s,"video/height")
  if h.isdigit():a["resolution"]="4K"if int(h)>=2000 else"1080P"if int(h)>=1000 else h+"P"
 o["stream"]=a;return o
def normalize_title(v):return re.sub(r"[\W_]+","",unicodedata.normalize("NFKC",v).casefold())
