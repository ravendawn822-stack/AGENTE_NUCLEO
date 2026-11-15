"""Bounded documentation ingest and dialogue. Documentation is data, never executable."""
import json,re,sys,unicodedata
from pathlib import Path
from skills import Oracle,synthesize,execute,export_python,OPS,RED
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"NUCLEO_V170_V215"))
from nucleus import Memory
def normalize(s):
    if type(s) is not str or len(s)>512:return ""
    return " ".join("".join(c for c in unicodedata.normalize("NFKD",s.casefold()) if not unicodedata.combining(c)).split())
def value(x,kind):
    if kind=="scalar":
        if type(x) is not int or abs(x)>10000:raise ValueError("integer")
        return x
    if type(x) is int and abs(x)<=1000000:return x
    if type(x) not in (list,tuple) or not 1<=len(x)<=32 or any(type(v) is not int or abs(v)>100000 for v in x):raise ValueError("vector")
    return tuple(x)
def parse_contract(doc):
    if type(doc) is not dict or set(doc)!={"name","kind","source","fit","pool","audit"}:raise ValueError("fields")
    name=doc["name"];kind=doc["kind"];source=doc["source"]
    if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}",name):raise ValueError("name")
    if kind not in ("scalar","vector") or type(source) is not str or not 1<=len(source)<=200:raise ValueError("metadata")
    seen=set();out=[]
    for key,lo,hi in (("fit",3,3),("pool",3,12),("audit",3,12)):
        data=doc[key]
        if type(data) is not list or not lo<=len(data)<=hi:raise ValueError("rows")
        rows=[]
        for row in data:
            if type(row) not in (list,tuple) or len(row)!=2:raise ValueError("row")
            x,y=[value(v,kind) for v in row]
            if kind=="vector" and not isinstance(x,tuple):raise ValueError("vector input")
            if x in seen:raise ValueError("duplicate input")
            seen.add(x);rows.append((x,y))
        out.append(rows)
    return name,kind,source,*out
class Registry:
    def __init__(self,path,macros=()):
        self.mem=Memory(path,resume=Path(path).exists());self.macros=tuple(tuple(m) for m in macros)
    def close(self):self.mem.close()
    def learn(self,doc):
        name,kind,source,fit,pool,audit=parse_contract(doc)
        if self.mem.get("skills:331",name) is not None:raise ValueError("duplicate skill")
        result=synthesize(fit,Oracle(pool),self.macros,True,kind)
        p=result["program"]
        verified=bool(p and all(execute(p,x)==y for x,y in audit))
        record=dict(status="document-audited" if verified else "rejected",source=source,kind=kind,
            program=p if verified else None,fit=fit,queries=result["queries"],audit=audit,candidates=result["candidates"])
        self.mem.put("skills:331",name,record)
        return record
    def apply(self,name,x):
        r=self.mem.get("skills:331",name)
        if not r or not r["program"]:raise ValueError("no validated skill")
        return execute(r["program"],x)
    def code(self,name):
        r=self.mem.get("skills:331",name)
        if not r or not r["program"]:raise ValueError("no validated skill")
        return export_python(r["program"])
    def respond(self,s):
        t=normalize(s)
        if t=="mostre habilidades":
            return dict(status="ok",skills=[dict(name=r[0],status=json.loads(r[1])["status"]) for r in self.mem.db.execute("SELECT key,value FROM knowledge WHERE scope='skills:331' ORDER BY key")])
        m=re.fullmatch(r"(explique|mostre codigo) ([a-z][a-z0-9_]{0,31})",t)
        if m:
            try:
                if m[1]=="mostre codigo":return dict(status="ok",code=self.code(m[2]))
                return dict(status="ok",record=self.mem.get("skills:331",m[2]))
            except ValueError as e:return dict(status="rejected",reason=str(e))
        m=re.fullmatch(r"aplique ([a-z][a-z0-9_]{0,31}) em (.+)",t)
        if m:
            try:return dict(status="ok",value=self.apply(m[1],json.loads(m[2])))
            except (ValueError,TypeError,KeyError):return dict(status="rejected",reason="entrada ou habilidade inválida")
        return dict(status="unknown",reason="comando fora da gramática; nenhuma ação")
