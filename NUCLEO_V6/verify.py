"""Independent CPython check of fixed-grammar synthesized fixture patches."""
import ast,json,sys
from pathlib import Path
from repair import safe_tree,patch
folder=Path(sys.argv[1]);rows=json.loads((folder/"exports.json").read_text());passed=checks=correct=0
for r in rows:
    path=folder/"fixtures"/r["file"];original=folder/"fixtures"/r["original"]
    assert path.parent==original.parent and path.name==r["file"] and original.name==r["original"]
    src=path.read_text()
    assert src==ast.unparse(patch(safe_tree(original.read_text()),r["edits"]))+"\n"
    safe_tree(src)
    # No builtins available, and the exact emitted source must match the restricted AST mutation.
    ns={"__builtins__":{}}
    exec(compile(src,str(path),"exec"),ns)
    ok=True
    for z,y,v in r["checks"]:
        try:a=ns["solve"](z)
        except (ValueError,ZeroDivisionError,TypeError):a=None
        assert a==v
        checks+=1;passed+=a==y;ok=ok and a==y
    correct+=ok
result=dict(functions=len(rows),checks=checks,passed=passed,correct=correct)
(folder/"python_verification.json").write_text(json.dumps(result,indent=2))
print("EXPORT_REPAIR="+json.dumps(result))
