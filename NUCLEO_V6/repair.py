"""V6: repair small standalone Python functions with a restricted AST interpreter.
Only generated fixtures are read; no arbitrary Python execution in the agent.
"""
import argparse,ast,copy,itertools,json,random,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SEEDS=(1440011,1470013,1500007)
CAP=256
QCAP=5
POLICIES=("fixed_single","active_single","active_double")
BIN={ast.Add:lambda a,b:a+b,ast.Sub:lambda a,b:a-b,ast.Mult:lambda a,b:a*b,ast.Mod:lambda a,b:a%b,ast.FloorDiv:lambda a,b:a//b}
CMP={ast.Lt:lambda a,b:a<b,ast.LtE:lambda a,b:a<=b,ast.Gt:lambda a,b:a>b,ast.GtE:lambda a,b:a>=b,ast.Eq:lambda a,b:a==b,ast.NotEq:lambda a,b:a!=b}
FIXTURES={
"shipping":("""def solve(items):
    total = 0
    for x in items:
        if x > 50:
            total += 0
        else:
            total += 5
    return total
""",lambda z:sum(5 for x in z if x<=50)),
"stock":("""def solve(items):
    total = 10
    for x in items:
        total += x
        if total < 0:
            total = 0
    return total
""",lambda z:stock(z)),
"discount":("""def solve(items):
    total = 0
    for x in items:
        if x >= 100:
            total += x - 10
        else:
            total += x
    return total
""",lambda z:sum(x-10 if x>=100 else x for x in z)),
"temperature":("""def solve(items):
    total = 0
    for x in items:
        if x < 0:
            total += 1
        if x > 30:
            total += 2
    return total
""",lambda z:sum((x<0)+2*(x>30) for x in z)),
"movement":("""def solve(items):
    previous = 0
    total = 0
    for x in items:
        if x > previous:
            total += x - previous
        previous = x
    return total
""",lambda z:sum(max(0,x-p) for p,x in zip((0,*z),z))),
"parity":("""def solve(items):
    total = 0
    for x in items:
        if x % 2 == 0:
            total += x
        else:
            total -= x
    return total
""",lambda z:sum(x if x%2==0 else -x for x in z)),
"points":("""def solve(items):
    total = 0
    for x in items:
        if x >= 0:
            total += x * 2
        else:
            total += x
    return total
""",lambda z:sum(2*x if x>=0 else x for x in z)),
"balance":("""def solve(items):
    total = 0
    for x in items:
        total += x
        if total > 100:
            total = 100
    return total
""",lambda z:balance(z)),
}
def stock(z):
    a=10
    for x in z:a=max(0,a+x)
    return a
def balance(z):
    a=0
    for x in z:a=min(100,a+x)
    return a

def safe_tree(src):
    # Normalize signed integer syntax and clone operator nodes individually:
    # ast.parse shares operator singleton objects across occurrences.
    class Normalize(ast.NodeTransformer):
        def visit_UnaryOp(self,n):
            if isinstance(n.op,ast.USub) and isinstance(n.operand,ast.Constant) and type(n.operand.value)==int:
                return ast.copy_location(ast.Constant(-n.operand.value),n)
            return self.generic_visit(n)
        def visit(self,n):
            if type(n) in (*BIN,*CMP):return type(n)()
            return super().visit(n)
    t=Normalize().visit(ast.parse(src))
    allowed=(ast.Module,ast.FunctionDef,ast.arguments,ast.arg,ast.For,ast.If,ast.Assign,ast.AugAssign,ast.Return,
             ast.Name,ast.Load,ast.Store,ast.Constant,ast.BinOp,ast.Compare,*BIN,*CMP)
    for n in ast.walk(t):
        if type(n) not in allowed:raise ValueError("unsupported syntax")
        if isinstance(n,ast.Name) and n.id not in ("items","x","total","previous"):raise ValueError("name")
        if isinstance(n,ast.Constant) and (type(n.value)!=int or abs(n.value)>200):raise ValueError("constant")
        if isinstance(n,ast.Compare) and len(n.ops)!=1:raise ValueError("comparison")
    if len(t.body)!=1 or t.body[0].name!="solve" or ast.unparse(t.body[0].args)!="items":raise ValueError("signature")
    return t

def evaluate(tree,z):
    if len(z)>32:raise ValueError("limit")
    env={"items":z}
    def expr(e):
        if isinstance(e,ast.Constant):return e.value
        if isinstance(e,ast.Name):return env[e.id]
        if isinstance(e,ast.BinOp):return BIN[type(e.op)](expr(e.left),expr(e.right))
        if isinstance(e,ast.Compare):return CMP[type(e.ops[0])](expr(e.left),expr(e.comparators[0]))
        raise ValueError("expression")
    def block(body):
        for s in body:
            if isinstance(s,ast.Assign):env[s.targets[0].id]=expr(s.value)
            elif isinstance(s,ast.AugAssign):env[s.target.id]=BIN[type(s.op)](env[s.target.id],expr(s.value))
            elif isinstance(s,ast.If):block(s.body if expr(s.test) else s.orelse)
            elif isinstance(s,ast.For):
                if s.iter.id!="items" or s.target.id!="x":raise ValueError("loop")
                for x in z:env["x"]=x;block(s.body)
            elif isinstance(s,ast.Return):return expr(s.value)
            else:raise ValueError("statement")
    return block(tree.body[0].body)

def mutations(t):
    for i,n in enumerate(ast.walk(t)):
        if type(n) in BIN:
            for typ in BIN:
                if typ!=type(n):yield (i,typ.__name__)
        elif type(n) in CMP:
            for typ in CMP:
                if typ!=type(n):yield (i,typ.__name__)
        elif isinstance(n,ast.Constant):
            for v in (n.value-1,n.value+1):
                if abs(v)<=200:yield (i,v)

def patch(tree,edits):
    t=copy.deepcopy(tree);nodes=list(ast.walk(t))
    classes={x.__name__:x for x in (*BIN,*CMP)}
    for i,v in edits:
        n=nodes[i]
        if isinstance(n,ast.Constant) and type(v)==int:n.value=v
        elif type(n) in (*BIN,*CMP) and isinstance(v,str):
            typ=classes[v]
            if (type(n) in BIN)!=(typ in BIN):raise ValueError("mutation category")
            n.__class__=typ
        else:raise ValueError("mutation")
    return t

def safe_eval(t,z):
    try:return evaluate(t,z)
    except (ValueError,ZeroDivisionError,KeyError,TypeError):return None

def suites(seed):
    rng=random.Random(seed)
    pool=[(),(-1,),(0,),(1,),(2,),(29,30,31),(49,50,51),(99,100,101),(-10,20,-30,40),(100,-120,20,100)]
    pool += [tuple(rng.choice((-120,-10,-1,0,1,2,29,30,31,49,50,51,99,100,101,120)) for _ in range(rng.randint(2,6))) for i in range(14)]
    pool=list(dict.fromkeys(pool))
    final=[*((x,) for x in (-150,-2,3,28,32,48,52,98,102,150)),*(tuple(rng.randint(-150,150) for _ in range(rng.randint(7,15))) for i in range(32))]
    final=list(dict.fromkeys(z for z in final if z not in pool))
    return pool,final

def candidate_edits(tree,allow_double):
    singles=list(mutations(tree));yield ()
    for e in singles:yield (e,)
    if allow_double:
        for a,b in itertools.combinations(singles,2):
            if a[0]!=b[0]:yield (a,b)

def repair(src,query,pool,policy):
    start=time.perf_counter_ns();tree=safe_tree(src);candidates=[]
    for edits in itertools.islice(candidate_edits(tree,policy=="active_double"),CAP):
        t=patch(tree,edits);sig=tuple(safe_eval(t,z) for z in pool)
        if all(v is not None and type(v)==int for v in sig):candidates.append((edits,sig))
    generated=min(CAP,sum(1 for _ in candidate_edits(tree,policy=="active_double")))
    history=[];unused=list(range(len(pool)))
    for j in range(QCAP):
        if not candidates:break
        signatures={sig for _,sig in candidates}
        if j and len(signatures)==1:break
        i=unused[0] if policy=="fixed_single" else max(unused,key=lambda k:(len({v[k] for v in signatures}),-k))
        unused.remove(i);y=query(pool[i]);before=len(candidates)
        candidates=[(e,s) for e,s in candidates if s[i]==y]
        history.append(dict(input=pool[i],output=y,before=before,after=len(candidates)))
    agreed=bool(candidates) and len({s for _,s in candidates})==1
    edits=candidates[0][0] if agreed else None
    out=ast.unparse(patch(tree,edits))+"\n" if edits is not None else None
    return out,dict(edits=edits,queries=history,candidates=generated,remaining=len(candidates),
        status="candidate" if agreed else "ambiguous" if candidates else "out_of_model",ns=time.perf_counter_ns()-start)

def run(folder):
    folder.mkdir(parents=True,exist_ok=False);rows=[];exports=[]
    fixtures=folder/"fixtures";fixtures.mkdir()
    for seed in SEEDS:
        rng=random.Random(seed);pool,final=suites(seed)
        for name,(src,reference) in FIXTURES.items():
            tree=safe_tree(src)
            assert all(safe_eval(tree,z)==reference(z) for z in pool+final)
            variants=list(mutations(tree))
            # Faults are sampled from the allowed mutation grammar, not from real issue history.
            one=rng.choice(variants)
            two=rng.choice([e for e in variants if e[0]!=one[0]])
            for family,edits in (("clean",()),("single",(one,)),("double",(one,two))):
                observed=ast.unparse(patch(tree,edits))+"\n"
                uid=f"{seed}_{name}_{family}";(fixtures/(uid+".py")).write_text(observed)
                for policy in POLICIES:
                    proposal,m=repair(observed,reference,pool,policy)
                    checks=[]
                    if proposal is not None:
                        t=safe_tree(proposal)
                        checks=[[z,reference(z),safe_eval(t,z)] for z in final]
                        if policy=="active_double":
                            file=uid+"_candidate.py";(fixtures/file).write_text(proposal)
                            exports.append(dict(file=file,original=uid+".py",edits=m["edits"],checks=checks))
                    success=proposal is not None and all(y==v for _,y,v in checks)
                    rows.append(dict(seed=seed,fixture=name,family=family,uid=uid,policy=policy,mutations=edits,
                      emitted=proposal is not None,success=success,exact=proposal==ast.unparse(tree)+"\n",
                      checks=checks,**m))
    def metric(rr):
        n=len(rr);ok=sum(r["success"] for r in rr);emitted=sum(r["emitted"] for r in rr)
        return dict(n=n,correct=ok,wrong=emitted-ok,abstained=n-emitted,exact=sum(r["exact"] for r in rr),
            mean_queries=sum(len(r["queries"]) for r in rr)/n,mean_candidates=sum(r["candidates"] for r in rr)/n,mean_ns=sum(r["ns"] for r in rr)/n)
    result=dict(protocol="V6-repair-v1",episodes=len(rows),exports=len(exports),
        aggregate=[dict(policy=p,**metric([r for r in rows if r["policy"]==p])) for p in POLICIES],
        by_family=[dict(policy=p,family=f,**metric([r for r in rows if r["policy"]==p and r["family"]==f])) for p in POLICIES for f in ("clean","single","double")])
    (folder/"summary.json").write_text(json.dumps(result,indent=2))
    (folder/"exports.json").write_text(json.dumps(exports,indent=2))
    with (folder/"raw.jsonl").open("w") as f:
        for row in rows:f.write(json.dumps(row)+"\n")
    print("SUMMARY_REPAIR="+json.dumps(result,separators=(",",":")))

class Tests(unittest.TestCase):
    def test_interpret(self):
        for src,ref in FIXTURES.values():
            self.assertEqual(evaluate(safe_tree(src),[-1,1,101,100]),ref([-1,1,101,100]))
    def test_mutation(self):
        tree=safe_tree(FIXTURES["points"][0]);m=next(mutations(tree));self.assertNotEqual(ast.unparse(tree),ast.unparse(patch(tree,[m])))
    def test_independent_operators_and_negative_constant(self):
        tree=safe_tree("def solve(items):\n    total = -1\n    for x in items:\n        total += x + 1\n    return total\n")
        i=next(i for i,n in enumerate(ast.walk(tree)) if isinstance(n,ast.Add))
        altered=patch(tree,[(i,"Sub")])
        self.assertEqual(sum(isinstance(n,ast.Sub) for n in ast.walk(altered)),1)
        self.assertEqual(sum(isinstance(n,ast.Add) for n in ast.walk(altered)),1)
        self.assertEqual(evaluate(tree,[2]),2)
    def test_reject(self):
        with self.assertRaises(ValueError):safe_tree("def solve(items):\n    return open('secret')")
    def test_repair(self):
        src="def solve(items):\n    total = 0\n    for x in items:\n        total -= x\n    return total\n"
        out,m=repair(src,sum,[(),(1,),(2,3),(-2,),(9,3)],"active_single")
        self.assertIsNotNone(out);self.assertEqual(evaluate(safe_tree(out),[4,5]),9)
        self.assertLessEqual(len(m["queries"]),QCAP)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--self-test",action="store_true");p.add_argument("--output",type=Path);a=p.parse_args()
    if a.self_test:raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful())
    if not a.output or ROOT not in a.output.resolve().parents:p.error("new output required")
    run(a.output)
