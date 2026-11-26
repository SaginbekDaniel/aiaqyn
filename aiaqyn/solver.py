"""Safe integer DSL: model output is never executed as Python or SMT source."""

import z3

from .schema import WitnessModel


def solve_witness(model: WitnessModel) -> dict:
    names = [v.name for v in model.variables]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate variable")
    variables = {name: z3.Int(name) for name in names}
    solver = z3.Solver()
    solver.set(timeout=2000)
    for v in model.variables:
        if v.minimum > v.maximum:
            raise ValueError("Invalid variable domain")
        solver.add(variables[v.name] >= v.minimum, variables[v.name] <= v.maximum)

    def expr(e):
        if e.variable is None:
            return z3.IntVal(e.offset)
        if e.variable not in variables:
            raise ValueError(f"Unknown variable: {e.variable}")
        return variables[e.variable] + e.offset

    def pred(p):
        a, b = expr(p.left), expr(p.right)
        return {"eq": a == b, "ne": a != b, "lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[p.op]

    guards = model.left.guard + model.right.guard
    if len(guards) > 100:
        raise ValueError("Too many predicates")
    solver.add(*[pred(p) for p in guards])
    reachable = solver.check()
    if reachable != z3.sat:
        return {"status": "unreachable" if reachable == z3.unsat else "unknown"}
    left, right = expr(model.left.output), expr(model.right.output)
    solver.add(left != right)
    status = solver.check()
    if status != z3.sat:
        return {"status": "no_divergence" if status == z3.unsat else "unknown"}
    witness = solver.model()
    return {
        "status": "divergence",
        "inputs": {k: witness.eval(v, model_completion=True).as_long() for k, v in variables.items()},
        "left_output": witness.eval(left).as_long(),
        "right_output": witness.eval(right).as_long(),
        "scope": "Verified only within the proposed integer model; semantic mapping needs human review.",
    }
