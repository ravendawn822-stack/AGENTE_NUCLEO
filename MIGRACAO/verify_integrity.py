"""Read-only byte verification; suitable for a fresh Git clone."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def verify(root=ROOT):
    manifest=json.loads((root/'MIGRACAO'/'inventario_original.json').read_text(encoding='utf-8'))
    failures=[]
    for row in manifest['files']:
        p=root/row['path']
        if not p.is_file() or p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:failures.append(row['path'])
    dbs=json.loads((root/'MIGRACAO'/'sqlite_verificacao.json').read_text(encoding='utf-8'))
    for row in dbs:
        p=root/row['snapshot']
        if not p.is_file() or sha(p)!=row['sha256']:failures.append(row['snapshot'])
    assert not failures,failures
    return dict(original_files=len(manifest['files']),sqlite_snapshots=len(dbs),all_hashes_match=True)
if __name__=='__main__':print(json.dumps(verify(),indent=2))
