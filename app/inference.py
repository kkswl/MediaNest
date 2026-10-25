import re
from pathlib import PurePosixPath
from guessit import guessit
def infer(filename,parent=""):
 g=guessit(filename);e=g.get("episode",[]);e=e if isinstance(e,list)else[e];s=g.get("season");s=s[0]if isinstance(s,list)and s else s;y=re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)",filename+" "+parent);t=str(g.get("title",""));r=filename.casefold();x=PurePosixPath(filename).suffix.lower();a={"format":"ISO"if x==".iso"else x[1:].upper(),"resolution":"4K"if"2160"in r else"1080P"if"1080"in r else"720P"if"720"in r else"未知","language":"国语"if"国语"in r else"原声"if"原声"in r else"未知","subtitle":"未知","evidence":"文件名推断，非音视频实测"};return{"title":t,"year":int(y[1])if y else None,"category":"tv"if e else"movie","season":s,"episodes":e,"attributes":a}
