"""V133–V138: state, actions, observed transition model and closed-loop planning."""
import random,sys
from collections import deque
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V92"))
from interpreter import execute,Invalid
N=8
MOVES=(0,1,2)
OPERATE=3
BUDGET=120
ROLES=("coletar","processar","entregar")
def layout(seed,changed=False):
    rng=random.Random(seed)
    ring=list(range(N));rng.shuffle(ring);a=rng.choice(MOVES)
    edges={(s,k):rng.randrange(N) for s in range(N) for k in MOVES}
    for i,s in enumerate(ring):edges[s,a]=ring[(i+1)%N]
    roles=dict(zip(rng.sample(range(N),3),ROLES))
    if changed:
        for k in rng.sample([k for k in edges if k[1]!=a],6):
            edges[k]=(edges[k]+rng.randrange(1,N))%N
    return edges,roles
class World:
    def __init__(self,seed,start=0,changed=False,cargo=3,programming=False,budget=BUDGET):
        if type(start) is not int or not 0<=start<N or type(budget) is not int or not 0<=budget<=BUDGET:raise ValueError("state")
        if type(cargo) is not int or not -8<=cargo<=8:raise ValueError("cargo")
        self.__edges,self.__roles=layout(seed,changed)
        self.room=start;self.phase=0;self.cargo=None;self.__input=cargo
        self.__programming=programming;self.used=0;self.budget=budget
    def observe(self):
        return dict(room=self.room,station=self.__roles.get(self.room),phase=self.phase,cargo=self.cargo,
            programming=self.__programming,remaining=self.budget-self.used,actions=MOVES+(OPERATE,))
    def act(self,action,program=None):
        if type(action) is not int or action not in MOVES+(OPERATE,) or self.used>=self.budget:raise ValueError("action/budget")
        self.used+=1
        if action in MOVES:self.room=self.__edges[self.room,action]
        elif self.phase<3 and self.__roles.get(self.room)==ROLES[self.phase]:
            if self.phase==0:self.cargo=self.__input
            elif self.phase==1:
                if self.__programming:
                    if program is None:return self.observe()
                    try:self.cargo=execute(program,self.cargo)
                    except Invalid:return self.observe()
                else:self.cargo+=1
            self.phase+=1
        return self.observe()
def path(edges,origin,goal,order=MOVES):
    q=deque([(origin,())]);seen={origin}
    while q:
        room,route=q.popleft()
        if goal(room):return route
        for a in order:
            k=(room,a)
            if k in edges and edges[k] not in seen:
                t=edges[k];seen.add(t);q.append((t,route+(a,)))
    return None
class Agent:
    def __init__(self,mode="directed",order=MOVES,seed=0,edges=None,stations=None,tools=None):
        if mode not in ("directed","reactive","random") or tuple(sorted(order))!=MOVES:raise ValueError("policy")
        self.mode=mode;self.order=tuple(order);self.rng=random.Random(seed)
        self.edges=dict(edges or {});self.stations=dict(stations or {});self.tools=dict(tools or {})
        self.events=[];self.decisions=0;self.macro_uses=0;self.divergences=0
    def perceive(self,obs):
        if obs["station"] is not None:self.stations[obs["station"]]=obs["room"]
    def record(self,before,a,after):
        expected=self.edges.get((before["room"],a)) if a in MOVES else None
        mismatch=expected is not None and expected!=after["room"]
        if a in MOVES:self.edges[before["room"],a]=after["room"]
        if mismatch:
            self.divergences+=1
            # All derived paths may be stale; retain only direct observations.
            self.tools.clear()
        self.perceive(after)
        self.events.append(dict(before=before,action=a,after=after,expected=expected,mismatch=mismatch))
        return mismatch
    def choose(self,obs,goal_room=None):
        self.perceive(obs);room=obs["room"];phase=obs["phase"]
        target=goal_room if goal_room is not None else self.stations.get(ROLES[phase]) if phase<3 else None
        if goal_room is None and phase<3 and obs["station"]==ROLES[phase] and self.mode!="random":return (OPERATE,),False
        if self.mode=="random":return (self.rng.choice(MOVES+(OPERATE,) if goal_room is None else MOVES),),False
        if self.mode=="reactive":return (self.rng.choice(MOVES),),False
        if target is not None:
            route=path(self.edges,room,lambda s:s==target,self.order)
            if route:
                macro=self.tools.get((room,target))
                if macro and tuple(macro)==route:return route,True
                return route[:1],False
        route=path(self.edges,room,lambda s:any((s,a) not in self.edges for a in self.order),self.order)
        if route is None:return (),False
        if route:return route[:1],False
        return (next(a for a in self.order if (room,a) not in self.edges),),False
    def solve(self,world,goal_room=None,program=None):
        if goal_room is not None and (type(goal_room) is not int or not 0<=goal_room<N):raise ValueError("goal")
        initial=world.used;d0=self.decisions;m0=self.macro_uses;v0=self.divergences;e0=len(self.events)
        while True:
            obs=world.observe();self.perceive(obs)
            if (obs["room"]==goal_room if goal_room is not None else obs["phase"]==3):break
            if not obs["remaining"]:break
            if goal_room is None and obs["phase"]==1 and obs["station"]=="processar" and obs["programming"] and program is None:break
            route,macro=self.choose(obs,goal_room);self.decisions+=1
            if not route:break
            if macro:self.macro_uses+=1
            for a in route:
                before=world.observe()
                if not before["remaining"]:break
                after=world.act(a,program if a==OPERATE else None)
                mismatch=self.record(before,a,after)
                if mismatch or (goal_room is not None and after["room"]==goal_room):break
                if a==OPERATE and before["phase"]==after["phase"] and before["programming"] and before["station"]=="processar":break
        end=world.observe()
        return dict(success=end["room"]==goal_room if goal_room is not None else end["phase"]==3,
            actions=world.used-initial,decisions=self.decisions-d0,macro_uses=self.macro_uses-m0,
            divergences=self.divergences-v0,end=end,events=self.events[e0:])
