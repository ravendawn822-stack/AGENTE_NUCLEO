"""Explicit finite observation interface, held values are kept by evaluator."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V109"))
import limits as lab
s=lab.s
DEV=tuple(78000019+30001*i for i in range(16))
DOMAIN=s.DOMAIN
class Oracle:
    def __init__(self,rows,limit):
        values=dict(rows)
        if len(values)!=len(rows) or type(limit) is not int or not 0<=limit<=len(values):raise ValueError("observation quota")
        self.__values=values;self.__limit=limit;self.events=[]
    def available(self):
        return tuple(sorted(set(self.__values)-{x for x,y in self.events}))
    def observe(self,x):
        if len(self.events)>=self.__limit or x not in self.available():raise ValueError("observation unavailable")
        y=self.__values[x];self.events.append((x,y));return y
def ambiguity(pool,known):
    states=sorted(set(DOMAIN)-{x for x,y in known})
    counts={x:len({h["values"][x-DOMAIN[0]] for h in pool}) for x in states}
    return dict(hypotheses=len(pool),unobserved=len(states),disagreement_states=sum(v>1 for v in counts.values()),distinct_outputs=counts)
