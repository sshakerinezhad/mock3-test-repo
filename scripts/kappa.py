"""KAPPA. Two mock-3-judge.py results.jsonl files -> agreement between the two judges.

    python scripts/kappa.py A/results.jsonl B/results.jsonl

Pairs rows on (task_id, run, criterion_id). Prints n paired, percent agreement, Cohen's kappa (grade.agreement,
the same formula `grade.py agree` uses) and each disagreement: task_name, criterion_id, A result, B result, both
reasons cut to 100 chars. Writes the disagreements to results/kappa_disagreements.md. A row with result null is a
judge failure, not a verdict: it is left out of the pairing and counted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, for grade
import grade

OUT = Path("results/kappa_disagreements.md")


def load(path: str) -> tuple[dict[tuple, dict], int]:
    """results.jsonl -> ({(task_id, run, criterion_id): row} for rows with a 0/1 result, number of null results)."""
    rows = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    good = {(r["task_id"], r["run"], r["criterion_id"]): r for r in rows if r["result"] in (0, 1)}
    return good, len(rows) - len(good)


def cut(s: str | None) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= 100 else s[:97] + "..."


def main(a_path: str, b_path: str) -> None:
    a, a_null = load(a_path)
    b, b_null = load(b_path)
    stats = grade.agreement({json.dumps(k): bool(r["result"]) for k, r in a.items()},
                            {json.dumps(k): bool(r["result"]) for k, r in b.items()})
    kappa = "undefined (both judges gave one answer on every pair: chance agreement is 100%)" \
        if stats["kappa"] is None else f"{stats['kappa']:.3f}"
    print(f"A: {a_path}  ({a_null} null results left out)\nB: {b_path}  ({b_null} null results left out)")
    print(f"n paired {stats['n']}  agreement {100 * stats['accuracy']:.1f}%  Cohen's kappa {kappa}")

    lines = ["| task | criterion | A | B | A reason | B reason |", "|---|---|---|---|---|---|"]
    for d in stats["disagreements"]:
        k = tuple(json.loads(d["id"]))
        ra, rb = a[k], b[k]
        print(f"  {ra['task_name']} | {k[2]} | A {ra['result']} | B {rb['result']}\n"
              f"    A: {cut(ra['reason'])}\n    B: {cut(rb['reason'])}")
        lines.append(f"| {ra['task_name']} | {k[2]} | {ra['result']} | {rb['result']} | "
                     f"{cut(ra['reason']).replace('|', '/')} | {cut(rb['reason']).replace('|', '/')} |")
    print(f"disagreements: {len(stats['disagreements'])}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(f"# Judge disagreements\n\nA: `{a_path}`  \nB: `{b_path}`  \n"
                   f"n paired {stats['n']}, agreement {100 * stats['accuracy']:.1f}%, kappa {kappa}\n\n"
                   + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python scripts/kappa.py A/results.jsonl B/results.jsonl")
    main(sys.argv[1], sys.argv[2])
