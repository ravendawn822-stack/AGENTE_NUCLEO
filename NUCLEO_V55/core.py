"""V55 core: bounded deterministic investigation, not a security sandbox."""
import sys
from pathlib import Path
from dataclasses import dataclass
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"NUCLEO_V54"))
import prediction_memory as previous

v,e,h,c,f,m=previous.v,previous.e,previous.h,previous.c,previous.f,previous.m
POLICIES={"direct":("direct",1),"motif_1024":("motif_lru",1024),
          "motif_8192":("motif_lru",8192),"motif_32768":("motif_lru",32768)}

@dataclass
class Task:
    examples: tuple
    context: str
    status: str="unseen"
    last_sha: str|None=None
    attempts: int=0

class Core:
    """Task-local contradictory evidence, shared pure predictions, positive library."""
    def __init__(self,base,policy):
        if policy not in POLICIES:raise ValueError("policy")
        self.library,_=v.extend(tuple(base),None,False)
        self.policy=policy
        self.prediction=previous.PredictionMemory(*POLICIES[policy])
        self.tasks={}
        self.negative={}
        self.events=[]
        self.frozen=False
    def mutable(self):
        if self.frozen:raise RuntimeError("frozen core")
    def observe(self,task,examples):
        self.mutable()
        examples=tuple((tuple(x),tuple(y) if y is not None else None) for x,y in examples)
        if not examples:raise ValueError("empty observations")
        if task in self.tasks:
            if self.tasks[task].examples!=examples:raise ValueError("changed observation context; use a new task")
            return
        self.tasks[task]=Task(examples,m.digest(examples))
    def eligible(self,task):
        t=self.tasks[task]
        return t.status=="unseen" or (t.status=="deferred" and t.last_sha!=m.digest(self.library))
    def investigate(self,task,validate):
        self.mutable()
        if not self.eligible(task):raise RuntimeError("ineligible investigation")
        t=self.tasks[task];before=self.library
        sha=m.digest(before);prior=t.status;prior_sha=t.last_sha
        cache=self.negative.setdefault(task,previous.NegativeMemory(t.examples,"paged")) if task not in self.negative else self.negative[task]
        pair,stats=previous.search(t.examples,before,self.prediction.mode,cache,self.prediction,task)
        memory=previous.memory_stats(self.negative)
        matches=checks=0;failure=None
        if pair is not None:
            # External validator owns reserved training inputs and labels.
            checks,matches,failure=validate(pair)
            if not (isinstance(checks,int) and isinstance(matches,int) and checks>0 and 0<=matches<=checks):
                raise ValueError("invalid validation evidence")
            if (matches==checks)!=(failure is None):raise ValueError("inconsistent validation evidence")
        accepted=pair is not None and matches==checks
        status="accepted" if accepted else ("rejected" if pair is not None else "deferred")
        self.library,added=v.extend(before,pair,accepted)
        t.status=status;t.last_sha=sha;t.attempts+=1
        if status!="deferred":self.negative.pop(task,None)
        row=dict(id=task,context=t.context,status=status,prior_status=prior,
            prior_trial_sha=prior_sha,before_sha=sha,after_sha=m.digest(self.library),
            before_size=len(before),after_size=len(self.library),added=added,
            pair=pair,emitted=pair is not None,accepted=accepted,
            recovered=accepted and prior=="deferred",validation_checks=checks,
            validation_matches=matches,validation_failure=failure,
            provenance=[dict(motif=p,individually_verified=False,source_pair_sha=m.digest(pair)) for p in added],
            cache_entries=sum(len(x) for x in self.negative.values()),**memory,
            prediction_entries=len(self.prediction.store),
            prediction_storage_bytes=self.prediction.storage_bytes(),**stats)
        self.events.append(row)
        return row
    def snapshot(self):
        # Ledger contains evidence; no oracle or final evaluation labels.
        return dict(policy=self.policy,library=self.library,library_sha=m.digest(self.library),
            frozen=self.frozen,tasks=[dict(id=i,context=t.context,status=t.status,
                 last_sha=t.last_sha,attempts=t.attempts) for i,t in self.tasks.items()],
            events=tuple(self.events))
    def freeze(self):
        self.mutable()
        self.frozen=True
        return self.library
