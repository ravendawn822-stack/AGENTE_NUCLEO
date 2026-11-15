"""Bounded primitive search in each branch, with explicit cost ledger."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V109"))
from limits import s
def solve_parts(option,budget):
    if type(budget) is not int or not 0<=budget<=s.CAP:raise ValueError("budget")
    if budget<3:return dict(parts=[],spent=0,programs=None)
    left=budget-1;parts=[]
    yes=s.search(option["yes"],False,cap=left//2)
    left-=yes["candidates"];parts.append(dict(branch="yes",**yes))
    if yes["program"] is None:return dict(parts=parts,spent=budget-1-left,programs=None)
    no=s.search(option["no"],False,cap=left)
    left-=no["candidates"];parts.append(dict(branch="no",**no))
    return dict(parts=parts,spent=budget-1-left,programs=(yes["program"],no["program"]) if no["program"] is not None else None)
