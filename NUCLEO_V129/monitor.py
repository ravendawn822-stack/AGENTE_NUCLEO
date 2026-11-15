"""Aggregate logged signals, distinguish evaluator outcomes from runtime observations."""
SEEDS=tuple(96000019+30001*i for i in range(24))
def summarize(rows,modes):
    result=[]
    for m in modes:
        rs=[r for r in rows if r["mode"]==m]
        result.append(dict(mode=m,tasks=len(rs),solved=sum(r["solved"] for r in rs),
            incorrect_programs=sum(r["emitted"] and not r["solved"] for r in rs),
            abstained_programs=sum(not r["emitted"] for r in rs),
            correct_predictions=sum(r["correct"] for r in rs),wrong_predictions=sum(r["wrong"] for r in rs),
            abstained_predictions=sum(r["abstained"] for r in rs),utility=sum(r["utility"] for r in rs),
            candidates=sum(r["candidates"] for r in rs),queries=sum(r["observations"] for r in rs),
            initial_pool=sum(r["search"].get("initial_pool",0) for r in rs),
            remaining_pool=sum(r["search"].get("remaining_pool",0) for r in rs),
            hypothesis_eliminations=sum(max(0,e["before"]-e["after"]) for r in rs for e in r["search"].get("query_events",[])),
            switch_attempts=sum(r["search"].get("switched",False) for r in rs),
            agreement_attempts=sum(r["search"].get("agreement_attempted",False) for r in rs),
            agreements=sum(r["search"].get("agreement",False) for r in rs),
            interpreter_evaluations=sum(r["search"].get("interpreter_evaluations",0) for r in rs),
            signature_evaluations=sum(r["search"].get("signature_evaluations",0) for r in rs),
            selected={a:sum(r["selected"]==a for r in rs) for a in sorted({r["selected"] for r in rs})}))
    return result
