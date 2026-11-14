"""Árvores matemáticas compactas e avaliáveis.

Não contém soluções dos desafios. A enumeração conhece apenas esta gramática.
"""
from dataclasses import dataclass
from typing import Tuple, Optional, Iterable

OP_ADD, OP_SUB, OP_MUL = 1, 2, 3
OP_CONST, OP_VAR = 10, 11
OP_NAMES = {OP_ADD: "+", OP_SUB: "-", OP_MUL: "*", OP_CONST: "c", OP_VAR: "x"}

@dataclass(frozen=True)
class Expr:
    op: int
    value: Optional[int] = None
    left: Optional["Expr"] = None
    right: Optional["Expr"] = None

    def evaluate(self, x: int) -> int:
        if self.op == OP_CONST: return int(self.value)
        if self.op == OP_VAR: return int(x)
        a, b = self.left.evaluate(x), self.right.evaluate(x)
        if self.op == OP_ADD: return a + b
        if self.op == OP_SUB: return a - b
        if self.op == OP_MUL: return a * b
        raise ValueError("operação desconhecida")

    def depth(self) -> int:
        if self.left is None: return 1
        return 1 + max(self.left.depth(), self.right.depth())

    def size(self) -> int:
        return 1 + (self.left.size() + self.right.size() if self.left else 0)

    def key(self) -> tuple:
        return (self.op, self.value, self.left.key() if self.left else None,
                self.right.key() if self.right else None)

    def text(self) -> str:
        if self.op == OP_VAR: return "x"
        if self.op == OP_CONST: return str(self.value)
        return "(" + self.left.text() + OP_NAMES[self.op] + self.right.text() + ")"

    def to_tuple(self):
        return (self.op, self.value, self.left.to_tuple() if self.left else None,
                self.right.to_tuple() if self.right else None)

    @staticmethod
    def from_tuple(t):
        op, value, left, right = t
        return Expr(op, value, Expr.from_tuple(left) if left else None,
                    Expr.from_tuple(right) if right else None)

def primitive_expressions() -> Iterable[Expr]:
    for c in (-2, -1, 0, 1, 2):
        yield Expr(OP_CONST, c)
    yield Expr(OP_VAR)

def combine(a: Expr, b: Expr) -> Iterable[Expr]:
    yield Expr(OP_ADD, left=a, right=b)
    yield Expr(OP_SUB, left=a, right=b)
    yield Expr(OP_MUL, left=a, right=b)

