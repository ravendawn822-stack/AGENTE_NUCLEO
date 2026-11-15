"""Distinguish absence of sampled hypotheses from proof of impossibility."""
SEEDS=tuple(90000019+30001*i for i in range(24))
def diagnose(rows):
    return dict(tasks=len(rows),initial_empty=sum(r["search"]["initial_pool"]==0 for r in rows),
        eliminated_all=sum(r["search"].get("eliminated_all",0)>0 for r in rows),
        expanded=sum(r["search"].get("expanded",False) for r in rows),
        recovered_pool=sum(r["search"].get("expansion_added",0)>0 for r in rows),
        final_empty=sum(r["search"]["remaining_pool"]==0 for r in rows),
        final_ambiguous=sum(r["search"]["remaining_pool"]>1 for r in rows),emitted=sum(r["emitted"] for r in rows))
