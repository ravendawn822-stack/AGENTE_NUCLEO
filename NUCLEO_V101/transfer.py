"""Frozen transfer to four previously unused target arrangements."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V100"))
import composition as c
s=c.syn
SEEDS=tuple(58000019+30001*i for i in range(24))
def cases(seed):
    targets=(s.branch("even","inc","neg")+s.seq("double","inc"),
             s.seq("inc","neg")+s.branch("negative","half","double"),
             s.repeat(3,"neg")+s.seq("inc","half","neg"),
             s.branch("negative","double","half")+s.repeat(2,"inc")+s.seq("mod3"))
    return [s.case(seed+997*j,p,"transfer") for j,p in enumerate(targets)]
