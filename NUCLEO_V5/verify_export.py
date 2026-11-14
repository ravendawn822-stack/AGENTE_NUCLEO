"""Separate evaluator of only the source regenerated from the fixed numeric compiler."""
import ast
import importlib.util
import json
import sys
from pathlib import Path
from contract import render

folder=Path(sys.argv[1])
rows=json.loads((folder/"export_checks.json").read_text())
source=(folder/"generated.py").read_text()
assert source=="\n".join(render(r["program"],r["name"]) for r in rows)
ast.parse(source)
spec=importlib.util.spec_from_file_location("generated",folder/"generated.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
ok=0;checks=0;passed=0;equivalent=0
for row in rows:
    f=getattr(module,row["name"]);valid=True
    for z,y,v in row["checks"]:
        try:actual=f(z)
        except (ValueError,ZeroDivisionError):actual=None
        assert actual==v
        checks+=1;passed+=actual==y;valid=valid and actual==y
    assert valid==row["interpreter_success"]
    ok+=valid;equivalent+=1
result=dict(functions=len(rows),equivalent=equivalent,correct=ok,checks=checks,passed=passed)
(folder/"export_verification.json").write_text(json.dumps(result,indent=2))
print("EXPORT_V5="+json.dumps(result))
