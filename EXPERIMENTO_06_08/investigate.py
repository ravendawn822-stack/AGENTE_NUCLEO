"""06/07A/08A: bounded project perception, active investigation and uncertainty.
Synthetic Python files only. No shell, imports of target code, eval, exec or external writes.
"""
import argparse
import ast
import json
import math
import random
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SEEDS=(104729,130363,155921,196613,262147)
FAMILIES=("single_fault","clean","double_fault")
POLICIES=("all_fixed","graph_fixed","graph_random","graph_active","graph_forced")
OPS=("+","-","*")
POOL=(-4,-3,-2,-1,0,1,2,3,4)
FIXED=(-2,0,3)
FINAL=tuple(range(-17,-4))+tuple(range(5,18))
CAP=28
QUERY_LIMIT=3


def source(name,expr,deps):
    imports="".join("from "+d+" import "+d+"\n" for d in sorted(deps))
    return imports+"def "+name+"(x):\n    return "+expr+"\n"


def build(seed,index,family):
    rng=random.Random(seed+1009*index)
    names=["f%02d"%i for i in range(10)];rng.shuffle(names)
    specs={}
    parents=[(),(0,),(0,),(1,),(2,),(3,4),(),(6,),(6,),(7,8)]
    for i,name in enumerate(names):
        p=parents[i];op=rng.choice(OPS);c=rng.randint(1,5)
        if not p:lhs="x";rhs=str(c)
        elif len(p)==1:
            lhs=names[p[0]]+"(x)"
            rhs="x" if i%3==2 else str(c)
        else:lhs=names[p[0]]+"(x)";rhs=names[p[1]]+"(x)"
        specs[name]=(lhs,op,rhs,tuple(names[j] for j in p))
    clean=dict(specs);changes=[]
    n={"clean":0,"single_fault":1,"double_fault":2}[family]
    for name in rng.sample(names[:6],n):
        l,op,h,deps=specs[name]
        if h.isdigit() and rng.randrange(2):
            new=str(int(h)+rng.choice((-1,1)));specs[name]=(l,op,new,deps)
            changes.append((name,"constant",int(h)))
        else:
            new=rng.choice([j for j in OPS if j!=op]);specs[name]=(l,new,h,deps)
            changes.append((name,"operator",op))
    render=lambda table:{name+".py":source(name,"("+l+" "+op+" "+h+")",deps) for name,(l,op,h,deps) in table.items()}
    return render(specs),render(clean),names[5],changes


class VirtualProject:
    def __init__(self,files):self.files=dict(files);self.reads=[]
    def list(self):return sorted(self.files)
    def read(self,path):
        self.reads.append(path)
        return self.files[path]


def parse_module(text,name):
    defs=[n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)]
    if len(defs)!=1 or defs[0].name!=name or len(defs[0].body)!=1 or not isinstance(defs[0].body[0],ast.Return):
        raise ValueError("not in supported grammar")
    e=defs[0].body[0].value
    deps={n.func.id for n in ast.walk(e) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    return e,deps


def perceive(project,entry,scope):
    allowed=set(project.list());expressions={};edges={}
    def visit(name):
        if name in expressions:return
        path=name+".py"
        if path not in allowed:raise ValueError("unknown path")
        e,deps=parse_module(project.read(path),name)
        expressions[name]=e;edges[name]=sorted(deps)
        for dep in sorted(deps):visit(dep)
    if scope=="all":
        for path in sorted(allowed):visit(path[:-3])
    else:visit(entry)
    return expressions,edges


def operator(node):
    return {ast.Add:"+",ast.Sub:"-",ast.Mult:"*"}[type(node)]


def evaluate(exprs,entry,x,patch=None):
    cache={}
    def call(name):
        if name in cache:return cache[name]
        local=patch if patch and patch[0]==name else None
        def ev(e,root=False):
            if isinstance(e,ast.Name) and e.id=="x":return x
            if isinstance(e,ast.Constant) and type(e.value)==int:return e.value
            if isinstance(e,ast.Call) and isinstance(e.func,ast.Name) and len(e.args)==1 and isinstance(e.args[0],ast.Name) and e.args[0].id=="x":
                return call(e.func.id)
            if isinstance(e,ast.BinOp):
                op=local[2] if root and local and local[1]=="operator" else operator(e.op)
                a=ev(e.left)
                b=local[2] if root and local and local[1]=="constant" else ev(e.right)
                return a+b if op=="+" else a-b if op=="-" else a*b
            raise ValueError("unsupported AST")
        out=ev(exprs[name],True);cache[name]=out
        return out
    return call(entry)


def candidates(expressions):
    yield None
    for name,e in sorted(expressions.items()):
        if not isinstance(e,ast.BinOp):continue
        for op in OPS:
            if op!=operator(e.op):yield (name,"operator",op)
        if isinstance(e.right,ast.Constant) and type(e.right.value)==int:
            for c in (e.right.value-1,e.right.value+1):yield (name,"constant",c)


def groups(survivors):
    return {sig for _,sig in survivors}


def informative(survivors,remaining):
    signatures=groups(survivors)
    def score(x):
        k=POOL.index(x);counts={}
        for sig in signatures:counts[sig[k]]=counts.get(sig[k],0)+1
        n=len(signatures)
        entropy=-sum((f/n)*math.log2(f/n) for f in counts.values())
        return entropy,abs(x),x
    return max(remaining,key=score)


def investigate(project,entry,query,policy,seed):
    start=time.perf_counter_ns()
    expressions,edges=perceive(project,entry,"all" if policy=="all_fixed" else "graph")
    indexed=[]
    for patch in candidates(expressions):
        if len(indexed)>=CAP:break
        indexed.append((patch,tuple(evaluate(expressions,entry,x,patch) for x in POOL)))
    survivors=indexed[:];remaining=list(POOL);history=[];rng=random.Random(seed)
    for i in range(QUERY_LIMIT):
        if not survivors or (i>0 and len(groups(survivors))==1):break
        if policy in ("graph_active","graph_forced"):x=informative(survivors,remaining)
        elif policy=="graph_random":x=rng.choice(remaining)
        else:x=FIXED[i]
        remaining.remove(x);y=query(x);k=POOL.index(x)
        before=len(survivors);gb=len(groups(survivors))
        survivors=[(p,s) for p,s in survivors if s[k]==y]
        history.append(dict(x=x,y=y,before=before,after=len(survivors),classes_before=gb,classes_after=len(groups(survivors))))
    classes=len(groups(survivors))
    if classes==0: status="out_of_model"
    elif classes==1:status="consensus"
    else:status="ambiguous"
    emitted=bool(survivors) and (classes==1 or policy=="graph_forced")
    patch=survivors[0][0] if emitted else None
    return patch,emitted,expressions,dict(status=status,remaining_hypotheses=len(survivors),remaining_classes=classes,
        confidence_proxy=1/classes if classes else 0.,files_read=len(project.reads),edges=edges,candidates=len(indexed),
        queries=history,search_ns=time.perf_counter_ns()-start)


def run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    rows=[];projects=[]
    for seed in SEEDS:
        for idx in range(60):
            family=FAMILIES[idx%3]
            observed,clean,entry,changes=build(seed,idx,family)
            truth,_=perceive(VirtualProject(clean),entry,"graph")
            projects.append(dict(seed=seed,index=idx,family=family,files=observed,clean=clean,entry=entry,changes=changes))
            for policy in POLICIES:
                patch,emitted,expr,m=investigate(VirtualProject(observed),entry,lambda x:evaluate(truth,entry,x),policy,seed+idx)
                ok=emitted and all(evaluate(expr,entry,x,patch)==evaluate(truth,entry,x) for x in FINAL)
                exact=emitted and ((not changes and patch is None) or (len(changes)==1 and patch==changes[0]))
                rows.append(dict(seed=seed,index=idx,family=family,policy=policy,patch=patch,emitted=emitted,success=ok,exact_repair=bool(exact),**m))
    def summary(rr):
        n=len(rr);correct=sum(x["success"] for x in rr);emitted=sum(x["emitted"] for x in rr)
        return dict(n=n,correct=correct,emitted=emitted,wrong=emitted-correct,abstained=n-emitted,
                    exact_repair=sum(x["exact_repair"] for x in rr),
                    mean_files=sum(x["files_read"] for x in rr)/n,
                    mean_candidates=sum(x["candidates"] for x in rr)/n,
                    mean_queries=sum(len(x["queries"]) for x in rr)/n,mean_search_ns=sum(x["search_ns"] for x in rr)/n)
    agg=[dict(policy=p,**summary([x for x in rows if x["policy"]==p])) for p in POLICIES]
    by_family=[dict(policy=p,family=f,**summary([x for x in rows if x["policy"]==p and x["family"]==f])) for p in POLICIES for f in FAMILIES]
    result=dict(protocol="06-08A-v1",episodes=len(rows),seeds=SEEDS,aggregate=agg,by_family=by_family)
    for file,items in (("raw.jsonl",rows),("projects.jsonl",projects)):
        with (folder/file).open("w",encoding="utf-8") as f:
            for row in items:f.write(json.dumps(row)+"\n")
    (folder/"summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print("SUMMARY_0608="+json.dumps(result))


class Tests(unittest.TestCase):
    def test_graph(self):
        observed,_,entry,_=build(4,0,"clean")
        p=VirtualProject(observed);e,edges=perceive(p,entry,"graph")
        self.assertEqual(len(e),6);self.assertEqual(len(p.reads),6)
        self.assertEqual(set(edges),set(e))
        all_e,_=perceive(VirtualProject(observed),entry,"all")
        self.assertEqual(len(all_e),10)
        self.assertEqual(evaluate(e,entry,3),evaluate(all_e,entry,3))
    def test_fault_reversible(self):
        for i in range(20):
            observed,clean,entry,changes=build(5,i,"single_fault")
            e,_=perceive(VirtualProject(observed),entry,"graph")
            truth,_=perceive(VirtualProject(clean),entry,"graph")
            self.assertIn(changes[0],list(candidates(e)))
            self.assertTrue(all(evaluate(e,entry,x,changes[0])==evaluate(truth,entry,x) for x in FINAL))
    def test_entropy(self):
        a=[(None,(0,)*len(POOL)),(("x","operator","+"),tuple(range(len(POOL))))]
        self.assertNotEqual(informative(a,list(POOL)),POOL[0])
    def test_refusal_and_budget(self):
        observed,clean,entry,_=build(8,0,"clean")
        p,emitted,e,m=investigate(VirtualProject(observed),entry,lambda x:10**50,"graph_active",8)
        self.assertFalse(emitted);self.assertEqual(m["status"],"out_of_model")
        self.assertLessEqual(len(m["queries"]),QUERY_LIMIT);self.assertLessEqual(m["candidates"],CAP)
        self.assertFalse(set(POOL)&set(FINAL))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if a.output is None or ROOT not in a.output.resolve().parents:p.error("new output inside EXPERIMENTO_06_08 required")
    run(a.output)
