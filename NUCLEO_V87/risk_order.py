"""Predefined scheduling and structural-impact options."""
import sys
from pathlib import Path
for v in (81,86):sys.path.insert(0,str(Path(__file__).resolve().parents[1]/f"NUCLEO_V{v}"))
from alternatives import ratio,signals
from audit_cycle import baseline,count0,count1,count2

def impact(i,c):
    s=signals([i],c.goals,c.graph,c.models,c.failed,c.blocked)
    return 2 if s[i][0]>=2 else 1

POLICIES={"baseline":(baseline,count0),"dfs_audit1":(baseline,count1),"dfs_audit2":(baseline,count2),
    "ratio":(ratio,count0),"ratio_audit1":(ratio,count1),"ratio_impact":(ratio,impact)}
