"""Oráculos independentes: expõem apenas consulta de caixa-preta."""
from expressions import Expr, OP_ADD, OP_SUB, OP_MUL, OP_CONST, OP_VAR

def c(n): return Expr(OP_CONST, n)
def x(): return Expr(OP_VAR)
def add(a,b): return Expr(OP_ADD, left=a, right=b)
def sub(a,b): return Expr(OP_SUB, left=a, right=b)
def mul(a,b): return Expr(OP_MUL, left=a, right=b)

class BlackBox:
    def __init__(self, name, hidden):
        self.name, self._hidden, self.calls = name, hidden, 0
    def query(self, value):
        self.calls += 1
        return self._hidden.evaluate(value)

def training_problems():
    return [BlackBox("T01", add(mul(c(2), x()), c(1))),
            BlackBox("T02", sub(mul(x(), x()), c(1))),
            BlackBox("T03", add(mul(c(3), x()), c(-2)))]

def novel_problems():
    return [BlackBox("N01", mul(add(mul(c(2), x()), c(1)), x())),
            BlackBox("N02", add(mul(x(), x()), add(x(), c(1)))),
            BlackBox("N03", sub(mul(add(x(), c(1)), add(x(), c(1))), c(1)))]

