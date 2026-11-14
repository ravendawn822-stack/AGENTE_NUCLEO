"""Run unchanged panels against a disposable, complete historical tree."""
import argparse,json,os,shutil,subprocess,sys,time
from pathlib import Path
from verify_integrity import ROOT,verify
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--panel',choices=['01','02'],default='02');args=parser.parse_args()
    verify();dest=ROOT/'WORKSPACES_EXECUCAO'/('painel_'+str(time.time_ns()));dest.mkdir(parents=True)
    files=json.loads((ROOT/'MIGRACAO'/'inventario_original.json').read_text(encoding='utf-8'))['files']
    for row in files:
        out=dest/row['path'];out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/row['path'],out)
    # Runtime copies use complete standalone backups. Original archived DB/WAL/SHM remain untouched.
    snapshots=json.loads((ROOT/'MIGRACAO'/'sqlite_verificacao.json').read_text(encoding='utf-8'))
    for d in snapshots:
        target=dest/d['original'];shutil.copy2(ROOT/d['snapshot'],target)
        for suffix in ('-wal','-shm','-journal'):
            side=Path(str(target)+suffix)
            if side.exists():side.unlink()  # only the newly generated runtime copy
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    print('Copia de execucao:',dest,flush=True)
    result=subprocess.run([sys.executable,'-B','panel.py'],cwd=dest/('PAINEL_'+args.panel),env=env)
    print('Novas sessoes preservadas em:',dest)
    print(json.dumps(verify(),indent=2));return result.returncode
if __name__=='__main__':sys.exit(main())
