"""Preserve source bytes; inspect SQLite only in disposable copies."""
import hashlib,json,re,shutil,sqlite3,tempfile,time
from pathlib import Path
SOURCE=Path(r'C:\Users\Administrator\Desktop\AGENTE_NUCLEO')
DEST=Path(r'C:\Users\Administrator\Documents\AGENTE_NUCLEO_GITHUB')
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def inventory(root):
    return [dict(path=p.relative_to(root).as_posix(),bytes=p.stat().st_size,sha256=digest(p))
        for p in sorted(root.rglob('*')) if p.is_file()]
def main():
    assert not DEST.exists(),'Destination already exists; refuse overwrite'
    files=inventory(SOURCE);DEST.mkdir(parents=True)
    for item in files:
        p=SOURCE/item['path'];assert not p.is_symlink()
        q=DEST/item['path'];q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
        assert digest(q)==item['sha256']
    meta=DEST/'MIGRACAO';meta.mkdir()
    (meta/'inventario_original.json').write_text(json.dumps(dict(source=str(SOURCE),files=files,
        count=len(files),bytes=sum(x['bytes'] for x in files)),indent=2),encoding='utf-8')
    rules={
        'github_token':rb'gh[pousr]_[A-Za-z0-9]{30,}',
        'github_pat':rb'github_pat_[A-Za-z0-9_]{40,}',
        'private_key':rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'aws_access_key':rb'AKIA[A-Z0-9]{16}',
        'openai_like_key':rb'sk-[A-Za-z0-9_-]{32,}',
        'credential_assignment':rb'(?i)(?:api_key|access_token|password|secret)\s*[=:]\s*[\x22\x27][^\x22\x27\r\n]{8,}[\x22\x27]',
        'email':rb'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
        'local_path':rb'(?i)[a-z]:[\\/](?:Users|otc-mobile)[\\/]',
    }
    findings=[]
    for item in files:
        p=DEST/item['path'];data=p.read_bytes()
        if p.name.lower() in ('.env','id_rsa','id_ed25519','credentials','hosts.yml'):
            findings.append(dict(path=item['path'],rule='sensitive_filename',count=1))
        for name,pattern in rules.items():
            matches=list(re.finditer(pattern,data))
            if matches:findings.append(dict(path=item['path'],rule=name,count=len(matches)))
    (meta/'seguranca.json').write_text(json.dumps(dict(findings=findings,
        note='Heuristic scan, including binary files; values are deliberately not recorded. Not a proof of absence.'),indent=2),encoding='utf-8')
    databases=[]
    for item in files:
        src=SOURCE/item['path']
        with src.open('rb') as f:header=f.read(16)
        if header!=b'SQLite format 3\x00':continue
        dest=meta/'sqlite_consistentes'/item['path'];dest.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='agente_sqlite_') as tmp:
            scratch=Path(tmp)/src.name;shutil.copy2(src,scratch)
            companions=[]
            for suffix in ('-wal','-shm','-journal'):
                side=Path(str(src)+suffix)
                if side.exists():shutil.copy2(side,Path(str(scratch)+suffix));companions.append(suffix)
            db=sqlite3.connect(str(scratch));check=[r[0] for r in db.execute('PRAGMA integrity_check')]
            assert check==['ok'],(item['path'],check)
            counts={name:db.execute('SELECT count(*) FROM "'+name.replace('"','""')+'"').fetchone()[0]
                for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            out=sqlite3.connect(str(dest));db.backup(out);out.execute('PRAGMA journal_mode=DELETE')
            assert out.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            out.close();db.close()
        databases.append(dict(original=item['path'],snapshot=dest.relative_to(DEST).as_posix(),
            sha256=digest(dest),bytes=dest.stat().st_size,integrity='ok',tables=counts,companions=companions))
    (meta/'sqlite_verificacao.json').write_text(json.dumps(databases,indent=2),encoding='utf-8')
    assert inventory(SOURCE)==files,'Source changed during preparation'
    summary=dict(files=len(files),original_bytes=sum(i['bytes'] for i in files),databases=len(databases),
        findings=findings,larger_than_50MiB=[i['path'] for i in files if i['bytes']>50*1024**2],
        source_unchanged=True)
    (meta/'preparacao.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
