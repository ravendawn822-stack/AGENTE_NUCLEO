"""No scientific runner is executed. Tests run from disposable copies."""
import ast,json,os,platform,shutil,sqlite3,subprocess,sys,tempfile
from pathlib import Path
from verify_integrity import verify,ROOT
def main():
    if '--require-linux' in sys.argv:assert sys.platform.startswith('linux'),'Linux runtime required'
    result=dict(platform=platform.platform(),python=sys.version,integrity=verify())
    files=json.loads((ROOT/'MIGRACAO'/'inventario_original.json').read_text(encoding='utf-8'))['files']
    python_files=[ROOT/r['path'] for r in files if r['path'].endswith('.py')]
    for p in python_files:ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p),feature_version=(3,12))
    result['python_sources_parsed_3_12']=len(python_files)
    databases=json.loads((ROOT/'MIGRACAO'/'sqlite_verificacao.json').read_text(encoding='utf-8'))
    for d in databases:
        db=sqlite3.connect((ROOT/d['snapshot']).resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';db.close()
    result['sqlite_integrity_checked']=len(databases)
    with tempfile.TemporaryDirectory(prefix='agente_portability_') as tmp:
        dest=Path(tmp)
        for name in ('model.py','engine.py','protocol.py','tests.py'):shutil.copy2(ROOT/'EXPERIMENTO_03'/name,dest/name)
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        test=subprocess.run([sys.executable,'-B','tests.py'],cwd=dest,env=env,capture_output=True,text=True)
        result['unit_tests_stdout']=test.stdout;result['unit_tests_stderr']=test.stderr
        assert test.returncode==0,result
    import tkinter
    root=tkinter.Tk();root.withdraw();root.update_idletasks();root.destroy();result['tkinter_smoke']='passed'
    result['integrity_after']=verify()
    print(json.dumps(result,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
