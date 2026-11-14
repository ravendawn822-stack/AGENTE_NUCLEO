"""External evaluator: execute only source reproduced by the fixed numeric compiler."""
import ast
import importlib.util
import json
import sys
from pathlib import Path
from planner import compiler,h

folder=Path(sys.argv[1]).resolve()
rows=json.loads((folder/"export_checks.json").read_text())
source=(folder/"generated.py").read_text()
expected=[]
for i,r in enumerate(rows):
    name=r["name"]
    assert name.startswith("task_") and name[5:].isdigit()
    p=h.freeze(r["program"])
    assert p[0]==30 and p[1]==0 and h.size(p[2])<=120
    expected.append(f"def {name}(items):\n    a = 0\n    for x in items:\n        a = {compiler(p[2])}\n    return a\n")
assert source=="\n".join(expected)
ast.parse(source)
spec=importlib.util.spec_from_file_location("generated",folder/"generated.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
checks=0
for r in rows:
    f=getattr(module,r["name"])
    for z,y,_ in r["cases"]:
        assert f(z)==y
        checks+=1
result=dict(exported_functions=len(rows),passed_checks=checks)
(folder/"export_verification.json").write_text(json.dumps(result,indent=2))
print("EXPORT_V4="+json.dumps(result))
