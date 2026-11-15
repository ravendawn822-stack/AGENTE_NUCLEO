"""Audit fit-selected programs without modifying or retrying them."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V93"))
from synthesis import matches,score,search
def assess(case,result,audit=True):
    p=result["program"]
    rejected=bool(p is not None and audit and not matches(p,case["audit"]))
    emitted=p is not None and not rejected
    return dict(**score(p if emitted else None,case["held"]),candidates=result["candidates"],
                emitted=int(emitted),rejected=int(rejected),program=p if emitted else None)
