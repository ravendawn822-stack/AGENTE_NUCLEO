"""Count predicted disagreements without consulting the target."""
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V115"))
from ambiguity import DOMAIN
def predict(h,x):return h["values"][x-DOMAIN[0]]
def scores(pool,states):
    return {x:len(pool)**2-sum(n*n for n in Counter(predict(h,x) for h in pool).values()) for x in states}
def choose(pool,states):
    values=scores(pool,states)
    if not values:raise ValueError("no states")
    return min(values,key=lambda x:(-values[x],x)),values
def retain(pool,x,y):return [h for h in pool if predict(h,x)==y]
