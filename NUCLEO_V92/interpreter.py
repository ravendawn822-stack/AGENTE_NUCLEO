"""Validated deterministic arithmetic interpreter; no external capabilities."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"NUCLEO_V91"))
from language import validate,Invalid,LIMIT,FUEL
def execute(program,value,fuel=FUEL,trace=None):
    p=validate(program)
    if type(value) is not int or abs(value)>LIMIT or type(fuel) is not int or not 0<=fuel<=FUEL:raise Invalid("input")
    remaining=fuel
    def block(b,x):
        nonlocal remaining
        for ins in b:
            remaining-=1
            if remaining<0:raise Invalid("fuel")
            op=ins[0];before=x
            if op=="inc":x+=1
            elif op=="neg":x=-x
            elif op=="double":x*=2
            elif op=="half":x//=2
            elif op=="mod3":x%=3
            elif op=="abs":x=abs(x)
            elif op=="if":
                condition=(x%2==0) if ins[1]=="even" else (x<0)
                x=block(ins[2] if condition else ins[3],x)
            elif op=="repeat":
                for _ in range(ins[1]):x=block(ins[2],x)
            else:raise Invalid("opcode")
            if abs(x)>LIMIT:raise Invalid("range")
            if trace is not None:trace.append(dict(operation=op,before=before,after=x,remaining=remaining))
        return x
    return block(p,value)
