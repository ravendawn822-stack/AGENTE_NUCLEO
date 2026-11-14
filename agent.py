import time, tracemalloc
from expressions import Expr, primitive_expressions, combine

class Agent:
    def __init__(self, name, memory=None, max_depth=4, budget=2000):
        self.name, self.memory, self.max_depth, self.budget = name, memory, max_depth, budget

    def _select_inputs(self, pool, count=4):
        """Escolhe consultas que separam previsões, sem usar respostas do oráculo."""
        candidates = []
        for i, h in enumerate(self._hypotheses()):
            if i >= 120: break
            candidates.append(h)
        chosen = []
        remaining = list(pool)
        while remaining and len(chosen) < count:
            best, best_score = remaining[0], -1
            for value in remaining:
                score = len({h.evaluate(value) for h in candidates})
                if score > best_score:
                    best, best_score = value, score
            chosen.append(best); remaining.remove(best)
        return chosen

    def _hypotheses(self):
        known = list(self.memory.skills()) if self.memory else []
        current = list(primitive_expressions()) + known
        seen = {e.key() for e in current}
        yield from current
        for _ in range(self.max_depth - 1):
            additions = []
            snapshot = list(current)
            for a in snapshot:
                for b in snapshot:
                    for e in combine(a, b):
                        if e.depth() <= self.max_depth and e.key() not in seen:
                            seen.add(e.key()); additions.append(e)
                            yield e
            current.extend(additions)

    def solve(self, oracle, train_inputs, validation_inputs):
        tracemalloc.start(); started = time.perf_counter()
        selected = self._select_inputs(train_inputs)
        observations = [(v, oracle.query(v)) for v in selected]
        hypotheses = experiments = 0; best = None
        for candidate in self._hypotheses():
            hypotheses += 1
            if hypotheses > self.budget: break
            ok = True
            for v, expected in observations:
                experiments += 1
                if candidate.evaluate(v) != expected:
                    ok = False; break
            if ok:
                best = candidate; break
        success = bool(best and all(best.evaluate(v) == oracle.query(v) for v in validation_inputs))
        if best and self.memory:
            # Apenas árvores realmente confirmadas entram na memória; subárvores
            # são habilidades descobertas, não soluções pré-carregadas.
            self.memory.save_skill(best)
            self._save_subexpressions(best)
        current, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
        return {"success": success, "expr": best.text() if best else None,
                "experiments": experiments, "hypotheses": hypotheses,
                "seconds": time.perf_counter()-started, "peak_kb": peak//1024,
                "calls": oracle.calls}

    def _save_subexpressions(self, e):
        if e.left is not None:
            self.memory.save_skill(e.left); self._save_subexpressions(e.left)
            self.memory.save_skill(e.right); self._save_subexpressions(e.right)

