import json, sqlite3, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
def freeze(e): return tuple(freeze(v) if isinstance(v,list) else v for v in e)
def text(e):
    if not e: return '—'
    if e[0]==10: return str(e[1])
    if e[0]==11: return 'x'
    return '('+text(e[1])+{1:'+',2:'−',3:'×'}[e[0]]+text(e[2])+')'
def depth(e): return 1 if e[0]>3 else 1+max(depth(e[1]),depth(e[2]))
def subs(e):
    if e and e[0]<=3:
        yield freeze(e)
        yield from subs(e[1]); yield from subs(e[2])
def hashes():
    return {str(p.relative_to(PROJECT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in PROJECT.rglob('*') if p.is_file() and ROOT not in p.parents}
def sources():
    return [p.parent for p in sorted((PROJECT/'EXPERIMENTO_02').glob('run_*/verification.json'))]+sorted((ROOT/'sessions').glob('*'))
def load(path):
    rows=[]
    with (path/'raw.jsonl').open(encoding='utf-8') as f:
        for line in f:
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: pass
    db=sqlite3.connect((path/'memory.sqlite3').as_uri()+'?mode=ro',uri=True)
    skills=[dict(zip(('seed','mode','agent','experience','expression'),r)) for r in db.execute('select seed,mode,agent,experience,expression from skills')]
    db.close()
    for s in skills: s['expression']=json.loads(s['expression'])
    return rows,skills
