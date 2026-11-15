"""Closed, finite arithmetic DSL. Programs are data, not Python source."""
OPS=("inc","neg","double","half","mod3","abs")
PREDS=("even","negative")
LIMIT=4096
NODES=32
DEPTH=4
FUEL=64
class Invalid(ValueError):pass
def validate(block):
    nodes=0
    def visit(b,depth):
        nonlocal nodes
        if depth>DEPTH or type(b) not in (tuple,list):raise Invalid("block")
        result=[];cost=0
        for i in b:
            nodes+=1
            if nodes>NODES or type(i) not in (tuple,list) or not i or type(i[0]) is not str:raise Invalid("instruction")
            op=i[0]
            if op in OPS and len(i)==1:result.append((op,));cost+=1
            elif op=="if" and len(i)==4 and type(i[1]) is str and i[1] in PREDS:
                a,ca=visit(i[2],depth+1);z,cz=visit(i[3],depth+1)
                result.append((op,i[1],a,z));cost+=1+max(ca,cz)
            elif op=="repeat" and len(i)==3 and type(i[1]) is int and i[1] in (2,3):
                a,ca=visit(i[2],depth+1);result.append((op,i[1],a));cost+=1+i[1]*ca
            else:raise Invalid("opcode or arguments")
        return tuple(result),cost
    p,cost=visit(block,1)
    if cost>FUEL:raise Invalid("static fuel")
    return p
def atoms(structured=True):
    p=tuple(((op,),) for op in OPS)
    if not structured:return p
    branch=p[:4]
    return p+tuple((("if",pred,a,b),) for pred in PREDS for a in branch for b in branch)+tuple((("repeat",n,a),) for a in p for n in (2,3))
