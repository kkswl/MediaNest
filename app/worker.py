import time,uuid
from sqlalchemy import func,or_,select,update
from .adapters import ReadError
from .db import Job,Node,Source,Task
from .health import record_health
from .metadata import TMDB,identify_directory,media_nodes
def start_scan(db,source):
 active=db.scalar(select(Job).where(Job.source_id==source.id,Job.status.in_(["queued","running","paused"])))
 if active:return active
 job=Job(source_id=source.id,owner_id=source.owner_id);db.add(job);db.flush();db.add(Task(job_id=job.id,source_id=source.id,kind="scan",target="0",dedupe_key=f"job:{job.id}:scan:0",payload={"offset":0,"path":""}));return job
class Worker:
 def __init__(self,database,settings,readers):self.database,self.settings,self.readers,self.tmdb=database,settings,readers,TMDB(settings)
 def claim(self,ignore_schedule=False):
  now=time.time()
  with self.database.session.begin() as db:
   db.execute(update(Task).where(Task.status=="running",Task.lease_until<now).values(status="queued",lease_token=""));q=select(Task).join(Source,Source.id==Task.source_id).outerjoin(Job,Job.id==Task.job_id).where(Task.status=="queued",Source.enabled.is_(True),or_(Task.job_id.is_(None),Job.status.in_(["queued","running"])))
   q=q.where(Source.adapter=="mock")if ignore_schedule else q.where(Task.available_at<=now,Source.next_request<=now);task=db.scalar(q.order_by(Task.available_at,Task.id).limit(1))
   if not task:return None
   lease=uuid.uuid4().hex
   if db.execute(update(Task).where(Task.id==task.id,Task.status=="queued").values(status="running",lease_until=now+self.settings.task_lease,lease_token=lease,attempts=Task.attempts+1,updated_at=now)).rowcount!=1:return None
   cond=[Source.id==task.source_id]
   if not ignore_schedule:cond.append(Source.next_request<=now)
   if db.execute(update(Source).where(*cond).values(next_request=now+self.settings.interval)).rowcount!=1:db.execute(update(Task).where(Task.id==task.id).values(status="queued",lease_token=""));return None
   if task.job_id:db.get(Job,task.job_id).status="running"
   return task.id,lease
 def tick(self,ignore_schedule=False):
  claimed=self.claim(ignore_schedule)
  if not claimed:return False
  tid,lease=claimed
  with self.database.session()as db:
   task=db.get(Task,tid);jid=task.job_id;source=db.get(Source,task.source_id)
   try:
    if task.kind=="scan":self.scan(db,task,source)
    elif task.kind=="identify":self.discover_media(db,task,source)
    elif task.kind=="identify_media":identify_directory(db,source,str(task.payload.get("directory","0")),self.readers,self.tmdb,media_node_id=int(task.target));task.status="done"
    elif task.kind=="health":self.health(db,task,source)
    with db.no_autoflush:fenced=db.execute(update(Task).where(Task.id==tid,Task.lease_token==lease,Task.lease_until>=time.time()).values(updated_at=time.time()).execution_options(synchronize_session=False))
    if fenced.rowcount!=1:db.rollback();return True
    task.lease_token="";task.lease_until=0;db.commit()
   except Exception as exc:
    db.rollback();task=db.get(Task,tid)
    if not task or task.lease_token!=lease:return True
    kind=exc.kind if isinstance(exc,ReadError) else"internal";task.error=f"{kind}: "+(str(exc)[:300]if isinstance(exc,ReadError)else type(exc).__name__)
    if kind in("timeout","rate_limited","uncertain")and task.attempts<4:task.status="queued";task.available_at=time.time()+min(300,2**task.attempts)
    else:task.status="failed";task.dedupe_key=None if task.kind=="health"else task.dedupe_key
    task.lease_token="";task.lease_until=0;db.commit()
  if jid:self.refresh_job(jid)
  return True
 def refresh_job(self,jid):
  with self.database.session.begin()as db:
   job=db.get(Job,jid)
   if not job or job.status in("paused","cancelled"):return
   c=dict(db.execute(select(Task.status,func.count()).where(Task.job_id==jid).group_by(Task.status)).all())
   if c.get("queued",0)+c.get("running",0)==0:job.status="partial"if c.get("failed",0)else"complete";job.finished_at=time.time();db.get(Source,job.source_id).last_scan=time.time()
 def scan(self,db,task,source):
  p=dict(task.payload);off=int(p.get("offset",0));items,total=self.readers.page(source,task.target,off,self.settings.page_size)
  if total<0 or len(items)>max(0,total-off)or(not items and off<total):raise ReadError("uncertain","分页未完整返回")
  if off and p.get("total")!=total:task.payload={"offset":0,"path":p.get("path","")};task.status="queued";return
  now=time.time()
  for item in items:
   node=db.scalar(select(Node).where(Node.source_id==source.id,Node.remote_id==item["id"]));path="/".join(x for x in(p.get("path",""),item["name"])if x)
   if not node:node=Node(source_id=source.id,remote_id=item["id"],parent_remote_id=task.target,name=item["name"],path=path,is_dir=item["is_dir"]);db.add(node)
   node.name,node.path,node.parent_remote_id=item["name"],path,task.target;node.size,node.sha1,node.public_image=item.get("size",0),item.get("sha1",""),item.get("public_image","");node.health,node.failures,node.checked_at,node.last_scan="healthy",0,now,now
   if node.is_dir:
    key=f"job:{task.job_id}:scan:{node.remote_id}"
    if not db.scalar(select(Task.id).where(Task.dedupe_key==key)):db.add(Task(job_id=task.job_id,source_id=source.id,kind="scan",target=node.remote_id,dedupe_key=key,payload={"offset":0,"path":path}))
  if task.target=="0"and off==0:record_health(db,source,None,"healthy","分享目录读取成功",self.settings)
  nxt=off+len(items);p.update(offset=nxt,total=total);task.payload=p
  if nxt<total:task.status="queued";task.available_at=now+self.settings.interval
  else:
   task.status="done";key=f"job:{task.job_id}:identify:{task.target}"
   if not db.scalar(select(Task.id).where(Task.dedupe_key==key)):db.add(Task(job_id=task.job_id,source_id=source.id,kind="identify",target=task.target,dedupe_key=key,payload={"cursor":0}))
 def discover_media(self,db,task,source):
  cur=int(task.payload.get("cursor",0));vals=db.scalars(media_nodes(source.id,task.target).where(Node.id>cur).order_by(Node.id).limit(25)).all()
  for n in vals:
   key=f"job:{task.job_id}:identify_media:{n.id}"
   if not db.scalar(select(Task.id).where(Task.dedupe_key==key)):db.add(Task(job_id=task.job_id,source_id=source.id,kind="identify_media",target=str(n.id),dedupe_key=key,payload={"directory":task.target}))
  if vals:task.payload={"cursor":vals[-1].id};task.status="queued";task.available_at=time.time()+self.settings.interval
  else:task.status="done"
 def health(self,db,task,source):
  node=db.get(Node,int(task.target))if task.target!="root"else None
  if task.target!="root"and(not node or node.source_id!=source.id):raise ReadError("internal","节点不属于来源")
  p=dict(task.payload);directory=node.parent_remote_id if node else"0";off=p.get("offset",0)
  try:
   items,total=self.readers.page(source,directory,off,self.settings.page_size)
   if total<0 or len(items)>max(0,total-off)or(not items and off<total):result,reason="uncertain","分页响应不完整"
   elif not node:result,reason="healthy","分享入口可读"
   elif off and p.get("total")!=total:result,reason="uncertain","目录变化"
   elif any(x["id"]==node.remote_id for x in items):result,reason="healthy","找到节点 ID"
   elif off+len(items)<total:task.payload={"offset":off+len(items),"total":total};task.status="queued";task.available_at=time.time()+self.settings.interval;return
   else:result,reason="missing","父目录完整读取后未找到节点"
  except ReadError as exc:result,reason=exc.kind,str(exc)
  record_health(db,source,node,result,reason,self.settings);task.status="done";task.dedupe_key=None;target=node or source
  if target.health=="pending":db.flush();db.add(Task(source_id=source.id,kind="health",target=task.target,dedupe_key=f"health:{source.id}:{task.target}",payload={"offset":0},available_at=time.time()+self.settings.recheck_delay))
 def drain(self,max_ticks=1000,ignore_schedule=True):
  i=0
  while i<max_ticks and self.tick(ignore_schedule):i+=1
  return i
