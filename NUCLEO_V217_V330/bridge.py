"""Shared typed V215 agenda plus generic external observation loop; no LLM."""
import sys, json, re, unicodedata
from pathlib import Path
from cognition import Learner
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"NUCLEO_V170_V215"))
from nucleus import Memory,Nucleus
class CognitiveCore:
    def __init__(self,path,actions,scope,seed=0,mode="active",order=("delta","constant","eq","le")):
        self.mem=Memory(path,resume=Path(path).exists());self.scope="cognitive:"+scope
        self.nucleus=Nucleus(seed=118000019,memory=self.mem,reuse=True)
        meta=self.mem.get(self.scope,"meta")
        expected=dict(actions=list(actions),mode=mode,order=list(order))
        if meta is None:self.mem.put(self.scope,"meta",expected)
        elif meta!=expected:raise ValueError("context or policy mismatch; use separate scope")
        self.learner=Learner(actions,mode,seed,order)
        for row in self.mem.db.execute("SELECT value FROM knowledge WHERE scope=? AND key LIKE 'e:%' ORDER BY key",(self.scope,)):
            e=json.loads(row[0]);self.learner.observe(tuple(e["before"]),e["action"],tuple(e["after"]),e["scores"])
        if len(self.learner.events)>4096:raise ValueError("quota")
        # Restore selection PRNG state along the observed trajectory, not world state.
        self.learner.rng.seed(seed+len(self.learner.events))
    def tick(self,env):
        if len(self.learner.events)>=4096:raise ValueError("action quota")
        e=self.learner.step(env);self.mem.put(self.scope,f"e:{e['step']:06d}",e)
        return e
    def learn_tool(self,fit,audit):
        i=self.nucleus.add("list_solve",dict(fit=fit,audit=audit))
        self.nucleus.run()
        return i
    def apply_tool(self,goal,x):
        i=self.nucleus.add("list_apply",dict(program=goal,input=x),(goal,))
        self.nucleus.run();return i
    def stats(self,goal):
        i=self.nucleus.add("stats",dict(source=goal),(goal,))
        self.nucleus.run();return i
    def ingest(self,name,value,source):
        if type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}",name):raise ValueError("name")
        if type(source) is not str or not 1<=len(source)<=200:raise ValueError("provenance")
        if type(value) not in (int,list) or (type(value) is list and len(value)>32):raise ValueError("value")
        if any(type(v) is not int or abs(v)>1000000 for v in ([value] if type(value) is int else value)):raise ValueError("value")
        # Data declared by provider, not independently verified knowledge.
        if self.mem.get("declared",name) is not None:raise ValueError("already exists")
        self.mem.put("declared",name,dict(value=value,source=source,status="declared"))
    def dialogue(self,message):
        if type(message) is not str or len(message)>160:return dict(status="unknown")
        t=" ".join("".join(c for c in unicodedata.normalize("NFKD",message.casefold()) if not unicodedata.combining(c)).strip().rstrip("?").split())
        if t in ("qual e seu estado","o que voce sabe"):return dict(status="ok",observation_model=self.learner.report(),memory=self.mem.counts())
        if t=="mostre a agenda":return dict(status="ok",agenda=self.mem.goals())
        m=re.fullmatch(r"mostre dado ([a-z][a-z0-9_]{0,31})",t)
        if m:return dict(status="ok",data=self.mem.get("declared",m[1]))
        return dict(status="unknown",detail="comando fora da gramática; nenhuma ação")
    def close(self):self.mem.close()
class SQM:
    """Only authorized local simulator endpoint; no access to its code, dimensions or files."""
    def __init__(self,port=8082):
        sys.path.insert(0,str(ROOT/"NUCLEO_V216_SQM"))
        from adapter import Remote
        self.remote=Remote(port);self.last=None
    def observe(self):
        self.last=self.remote.observe();return self.last
    def act(self,a):
        if self.last is None:raise ValueError("missing observation")
        self.last=self.remote.act(a,self.last);return self.last
