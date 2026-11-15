"""Local trusted checkpoints. SHA-256 detects accidental corruption, not authenticity."""
import hashlib,json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V55"))
from core import Core,Task,POLICIES,previous,v,e,h,c,f,m
SCHEMA=1
MAX_BYTES=32*1024*1024

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()
def tup(value):
    return tuple(tup(x) for x in value) if isinstance(value,list) else value
def fingerprint():
    files=[ROOT.parent/"NUCLEO_V55"/"core.py"]
    files.extend(Path(mod.__file__) for mod in (previous,v,e,h,c,f,m))
    return digest([m.digest(c.MOTIFS),*[hashlib.sha256(p.read_bytes()).hexdigest() for p in files]])

def capture(core,cursor):
    if type(cursor) is not int or not 0<=cursor<=previous.ATTEMPTS:raise ValueError("cursor")
    return dict(schema=SCHEMA,fingerprint=fingerprint(),cursor=cursor,policy=core.policy,
        library=core.library,frozen=core.frozen,
        tasks=[dict(id=i,examples=t.examples,context=t.context,status=t.status,last_sha=t.last_sha,
                    attempts=t.attempts) for i,t in core.tasks.items()],
        negative=[dict(id=i,context=n.context,count=len(n),
                    pages=[[p,b.hex()] for p,b in sorted(n.store.items())]) for i,n in core.negative.items()],
        predictions=[[k,value,origin] for k,(value,origin) in core.prediction.store.items()],
        stats=core.prediction.stats,events=core.events)

def write_checkpoint(path,core,cursor):
    path=Path(path)
    data=capture(core,cursor)
    encoded=canonical(dict(payload=data,sha256=digest(data)))
    if len(encoded)>MAX_BYTES:raise ValueError("checkpoint too large")
    if path.exists():raise FileExistsError(path)
    # Same filesystem; link publishes only fully written data and refuses replacement.
    fd,name=tempfile.mkstemp(prefix=".checkpoint-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as fp:
            fp.write(encoded);fp.flush();os.fsync(fp.fileno())
        os.link(name,path)
    finally:
        os.unlink(name)
    return len(encoded)

def read_checkpoint(path,discard_predictions=False):
    with Path(path).open("rb") as fp:raw=fp.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError("checkpoint too large")
    envelope=json.loads(raw);data=envelope["payload"]
    if envelope["sha256"]!=digest(data):raise ValueError("checkpoint checksum")
    if data["schema"]!=SCHEMA or data["fingerprint"]!=fingerprint():raise ValueError("incompatible checkpoint")
    cursor=data["cursor"]
    if type(cursor) is not int or not 0<=cursor<=previous.ATTEMPTS:raise ValueError("cursor")
    if type(data["frozen"]) is not bool:raise ValueError("frozen")
    core=Core(tup(data["library"]),data["policy"])
    for row in data["tasks"]:
        i=row["id"]
        if type(i) is not int or i<0 or i in core.tasks:raise ValueError("task identity")
        core.observe(i,tup(row["examples"]));t=core.tasks[i]
        if t.context!=row["context"]:raise ValueError("observation checksum")
        status,attempts,last=row["status"],row["attempts"],row["last_sha"]
        if (status not in ("unseen","accepted","rejected","deferred") or type(attempts) is not int
            or not 0<=attempts<=cursor or (status=="unseen")!=(attempts==0)
            or (attempts==0)!=(last is None)):raise ValueError("task state")
        t.status=status;t.attempts=attempts;t.last_sha=last
    for row in data["negative"]:
        i=row["id"]
        if i in core.negative or core.tasks[i].status!="deferred":raise ValueError("negative task")
        cache=previous.NegativeMemory(core.tasks[i].examples,"paged")
        if cache.context!=row["context"]:raise ValueError("negative context")
        count=0
        for page,hexdata in row["pages"]:
            if type(page) is not int or page<0 or page*previous.PAGE_BITS>=previous.UNIVERSE or page in cache.store:
                raise ValueError("invalid page")
            b=bytearray.fromhex(hexdata)
            if len(b)!=previous.PAGE_BYTES:raise ValueError("invalid bitmap size")
            valid=min(previous.PAGE_BITS,previous.UNIVERSE-page*previous.PAGE_BITS)
            bits=int.from_bytes(b,"little")
            if bits>>valid or bits==0:raise ValueError("invalid bitmap bits")
            count+=bits.bit_count();cache.store[page]=b
        if count!=row["count"] or count>previous.CACHE_CAP:raise ValueError("negative count")
        cache.count=count;core.negative[i]=cache
    if set(core.negative)!={i for i,t in core.tasks.items() if t.status=="deferred"}:raise ValueError("missing negative memory")
    stats=data["stats"]
    if set(stats)!=set(core.prediction.stats) or any(type(x) is not int or x<0 for x in stats.values()):
        raise ValueError("prediction stats")
    core.prediction.stats=dict(stats)
    entries=data["predictions"]
    if len(entries)>core.prediction.capacity or (core.prediction.mode=="direct" and entries):
        raise ValueError("prediction limit")
    for rawkey,rawvalue,origin in entries:
        key=tup(rawkey);value=tup(rawvalue)
        if (len(key)!=2 or key[0] not in c.MOTIF_SET or not isinstance(key[1],tuple)
            or any(type(x) is not int for x in key[1]) or origin not in core.tasks
            or (value is not None and (not isinstance(value,tuple) or any(type(x) is not int for x in value)))
            or key in core.prediction.store):raise ValueError("prediction entry")
        core.prediction.store[key]=(value,origin)
    if discard_predictions:core.prediction.store.clear()
    core.events=data["events"]
    if len(core.events)!=sum(t.attempts for t in core.tasks.values()) or len(core.events)>cursor:raise ValueError("event count")
    core.frozen=data["frozen"]
    return core,cursor
