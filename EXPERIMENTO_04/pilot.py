"""Experiment 04: controlled algorithm acquisition pilot (stdlib only).
No historical writes. This is an infrastructure smoke test, not a benchmark.
"""
import argparse
import hashlib
import inspect
import json
import sqlite3
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROBES = tuple(range(-4, 5))
HELD_OUT = (-11, -9, -7, 7, 9, 11)


def polynomial(observations):
    # Exact Lagrange interpolation. Known assumptions are supplied by the source.
    points = tuple((Fraction(x), Fraction(y)) for x, y in observations)
    def predict(x):
        x = Fraction(x)
        result = Fraction(0)
        for i, (xi, yi) in enumerate(points):
            term = yi
            for j, (xj, _) in enumerate(points):
                if i != j:
                    term *= (x-xj)/(xi-xj)
            result += term
        return result
    return predict


def periodic(observations):
    for period in range(1, 6):
        table = {}
        for x, y in observations:
            key = x % period
            if key in table and table[key] != y:
                break
            table[key] = y
        else:
            if len(table) == period:
                return lambda x: table[x % period]
    return None


def constant(observations):
    values = {y for _, y in observations}
    if len(values) == 1:
        value = next(iter(values))
        return lambda x: value
    return None


# Trusted developer supplied catalog. Not arbitrary downloaded Python.
CATALOG = {
    "constant": (constant, "constant integer-valued functions"),
    "periodic": (periodic, "integer period up to 5; complete residue coverage"),
    "polynomial": (polynomial, "univariate polynomial degree <= 8; 9 distinct points"),
}


def source_hash(fn):
    return hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()


def assess(fn, target):
    obs = tuple((x, target(x)) for x in PROBES)
    pred = fn(obs)
    checks = [(x, target(x), None if pred is None else str(pred(x)))
              for x in HELD_OUT]
    valid = pred is not None and all(pred(x) == y for x, y, _ in checks)
    return valid, checks


class Library:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS skills(
          name TEXT PRIMARY KEY, version TEXT NOT NULL, scope TEXT NOT NULL,
          evidence TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
          id INTEGER PRIMARY KEY, kind TEXT, payload TEXT);
        """)
    def event(self, kind, **payload):
        self.db.execute("INSERT INTO events(kind,payload) VALUES(?,?)",
                        (kind, json.dumps(payload, sort_keys=True)))
    def acquire(self, name, fixtures):
        fn, scope = CATALOG[name]
        version = source_hash(fn)
        evidence = []
        self.event("skill_received", name=name, source="controlled_external", version=version)
        # All positive AND negative fixtures must agree with expected behavior.
        for target, expected in fixtures:
            valid, checks = assess(fn, target)
            evidence.append(dict(expected=expected, observed=valid, checks=checks))
        passed = bool(evidence) and all(e["expected"] == e["observed"] for e in evidence)
        self.event("skill_tested", name=name, passed=passed, evidence=evidence)
        if passed:
            self.db.execute("INSERT OR REPLACE INTO skills VALUES(?,?,?,?)",
                            (name, version, scope, json.dumps(evidence)))
        else:
            # A failed requalification invalidates the previous active record.
            self.db.execute("DELETE FROM skills WHERE name=?", (name,))
        self.event("skill_acquired" if passed else "skill_rejected", name=name)
        self.db.commit()
        return passed
    def active(self):
        result = {}
        for name, version in self.db.execute("SELECT name,version FROM skills ORDER BY name"):
            if name in CATALOG and source_hash(CATALOG[name][0]) == version:
                result[name] = CATALOG[name][0]
        return result
    def close(self):
        self.db.close()


def pilot(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    dbpath = folder / "memory.sqlite3"
    lib = Library(dbpath)
    fixtures = {
        "constant": [(lambda x: 3, True), (lambda x: x, False)],
        "periodic": [(lambda x: x % 3, True), (lambda x: x*x, False)],
        "polynomial": [(lambda x: x*x+2*x-1, True), (lambda x: x % 3, False)],
    }
    try:
        initial = list(lib.active())
        outcomes = {name: lib.acquire(name, cases) for name, cases in fixtures.items()}
    finally:
        lib.close()
    lib = Library(dbpath)
    try:
        # Demonstrates persistence and transfer on separate functions, no ranking or learning here.
        targets = {"constant_new": lambda x: -7,
                   "periodic_new": lambda x: (x % 4)**2,
                   "polynomial_new": lambda x: 3*x**3-x+4,
                   "unsupported_step": lambda x: -3 if x < 0 else 9}
        rows = []
        for label, target in targets.items():
            for name, fn in lib.active().items():
                valid, checks = assess(fn, target)
                row = dict(problem=label, skill=name, success=valid, checks=checks)
                rows.append(row)
                lib.event("pilot_evaluation", **row)
        lib.db.commit()
        result = dict(kind="infrastructure_pilot_not_scientific_benchmark",
                      initially_active=initial, acquisition=outcomes,
                      after_reopen=list(lib.active()), evaluations=rows)
    finally:
        lib.close()
    (folder/"result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


class Tests(unittest.TestCase):
    def test_polynomial_exact(self):
        target = lambda x: 2*x**8-5*x+1
        self.assertTrue(assess(polynomial, target)[0])
    def test_periodic_and_rejection(self):
        self.assertTrue(assess(periodic, lambda x: x % 5)[0])
        self.assertFalse(assess(periodic, lambda x: x*x)[0])
    def test_rejected_not_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib = Library(Path(tmp)/"memory.sqlite3")
            try:
                self.assertFalse(lib.acquire("constant", [(lambda x: x, True)]))
                self.assertEqual(lib.active(), {})
            finally:
                lib.close()
    def test_persistence_and_transfer(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = pilot(Path(tmp)/"new")
            self.assertEqual(result["initially_active"], [])
            self.assertTrue(all(result["acquisition"].values()))
            self.assertEqual(set(result["after_reopen"]), set(CATALOG))
            rows = {(r["problem"],r["skill"]):r["success"] for r in result["evaluations"]}
            self.assertTrue(rows["constant_new","constant"])
            self.assertTrue(rows["periodic_new","periodic"])
            self.assertTrue(rows["polynomial_new","polynomial"])
            self.assertFalse(any(v for (p,_),v in rows.items() if p=="unsupported_step"))
            with self.assertRaises(FileExistsError):
                pilot(Path(tmp)/"new")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--pilot", type=Path)
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
        raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
    if args.pilot is None:
        parser.error("use --self-test or --pilot NEW_DIRECTORY")
    folder = args.pilot.resolve()
    if folder == ROOT or ROOT in folder.parents:
        # Only fresh paths under this experiment are allowed here.
        pass
    else:
        parser.error("pilot output must be inside EXPERIMENTO_04")
    result = pilot(folder)
    print(json.dumps(result, indent=2))
