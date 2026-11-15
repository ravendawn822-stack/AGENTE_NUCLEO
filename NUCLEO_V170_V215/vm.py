"""V176–183: finite typed list/integer VM. Programs are declarative data."""
MAX_N=32
MAX_INT=1000000
FUEL=256
class Invalid(ValueError):pass
def value(x):
    if type(x) is int and abs(x)<=MAX_INT:return x
    if type(x) in (list,tuple) and len(x)<=MAX_N and all(type(n) is int and abs(n)<=MAX_INT for n in x):return tuple(x)
    raise Invalid("value limit/type")
def integer(x):
    if type(x) is not int:raise Invalid("integer")
    return x
def array(x):
    if type(x) is not tuple:raise Invalid("array")
    return x
ARITY={"add":2,"mul":2,"ge":2,"ne":2,"contains":2,"append":2,"reverse":1,"sort":1,"sum":1,"count":1}
def validate(p):
    if type(p) not in (tuple,list) or not 1<=len(p)<=8:raise Invalid("functions")
    nodes=0
    def node(x,depth):
        nonlocal nodes
        nodes+=1
        if nodes>256 or depth>12 or type(x) not in (list,tuple) or not x or type(x[0]) is not str:raise Invalid("AST")
        return x[0]
    def var(i):
        if type(i) is not int or not 0<=i<8:raise Invalid("variable")
    def expr(e,fi,d):
        op=node(e,d)
        if op=="const" and len(e)==2:value(e[1])
        elif op=="var" and len(e)==2:var(e[1])
        elif op=="call" and len(e)==3 and type(e[1]) is int and 0<=e[1]<fi:expr(e[2],fi,d+1)
        elif op in ARITY and len(e)==1+ARITY[op]:
            for arg in e[1:]:expr(arg,fi,d+1)
        else:raise Invalid("expression")
    def block(b,fi,d):
        if type(b) not in (tuple,list) or d>12 or not 1<=len(b)<=32:raise Invalid("block")
        for ins in b:
            op=node(ins,d)
            if op=="set" and len(ins)==3:var(ins[1]);expr(ins[2],fi,d+1)
            elif op=="return" and len(ins)==2:expr(ins[1],fi,d+1)
            elif op=="if" and len(ins)==4:
                expr(ins[1],fi,d+1);block(ins[2],fi,d+1);block(ins[3],fi,d+1)
            elif op=="for" and len(ins)==4:var(ins[1]);expr(ins[2],fi,d+1);block(ins[3],fi,d+1)
            else:raise Invalid("instruction")
    for i,b in enumerate(p):block(b,i,1)
    return p
def execute(program,x,fuel=FUEL):
    p=validate(program)
    if type(fuel) is not int or not 0<=fuel<=FUEL:raise Invalid("fuel")
    remaining=fuel
    def tick():
        nonlocal remaining
        remaining-=1
        if remaining<0:raise Invalid("fuel")
    def call(fi,arg):
        regs={0:value(arg)}
        def exp(e):
            tick();op=e[0]
            if op=="const":return value(e[1])
            if op=="var":
                if e[1] not in regs:raise Invalid("undefined variable")
                return regs[e[1]]
            if op=="call":return call(e[1],exp(e[2]))
            a=[exp(v) for v in e[1:]]
            if op=="add":r=integer(a[0])+integer(a[1])
            elif op=="mul":r=integer(a[0])*integer(a[1])
            elif op=="ge":r=int(integer(a[0])>=integer(a[1]))
            elif op=="ne":r=int(a[0]!=a[1])
            elif op=="contains":r=int(integer(a[1]) in array(a[0]))
            elif op=="append":r=array(a[0])+(integer(a[1]),)
            elif op=="reverse":r=array(a[0])[::-1]
            elif op=="sort":r=tuple(sorted(array(a[0])))
            elif op=="sum":r=sum(array(a[0]))
            elif op=="count":r=len(array(a[0]))
            else:raise Invalid("operation")
            return value(r)
        def run(block):
            for ins in block:
                tick();op=ins[0]
                if op=="set":regs[ins[1]]=exp(ins[2])
                elif op=="return":return True,exp(ins[1])
                elif op=="if":
                    returned,result=run(ins[2] if integer(exp(ins[1])) else ins[3])
                    if returned:return returned,result
                elif op=="for":
                    for item in array(exp(ins[2])):
                        tick();regs[ins[1]]=item;returned,result=run(ins[3])
                        if returned:return returned,result
            return False,None
        ok,result=run(p[fi])
        if not ok:raise Invalid("no return")
        return value(result)
    return call(len(p)-1,value(x))
ATOMS=("double","inc","reverse","sort","nonnegative","nonzero","unique","sum","count")
def atom(name):
    x=("var",0);out=("var",1);item=("var",2)
    if name in ("reverse","sort","sum","count"):return (("return",(name,x)),)
    if name not in ATOMS:raise Invalid("atom")
    if name=="double":body=(("set",1,("append",out,("mul",item,("const",2)))),)
    elif name=="inc":body=(("set",1,("append",out,("add",item,("const",1)))),)
    else:
        cond=("ge",item,("const",0)) if name=="nonnegative" else ("ne",item,("const",0)) if name=="nonzero" else ("ne",("contains",out,item),("const",1))
        body=(("if",cond,(("set",1,("append",out,item)),),(("set",1,out),)),)
    return (("set",1,("const",())),("for",2,x,body),("return",out))
def compile_pipeline(seq):
    if type(seq) not in (tuple,list) or not 1<=len(seq)<=3:raise Invalid("pipeline")
    funcs=tuple(atom(a) for a in seq);e=("var",0)
    for i in range(len(seq)):e=("call",i,e)
    return validate(funcs+((("return",e),),))
def run_pipeline(seq,x):return execute(compile_pipeline(seq),x)
