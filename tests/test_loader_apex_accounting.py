import json
from pathlib import Path

import pytest

import grade
import run
from loaders import apex_accounting as apex

DEV = Path("data/apex/data/dev.jsonl")
pytestmark = pytest.mark.skipif(not DEV.exists(), reason="data/ is gitignored; needs the APEX-Accounting dev set")

T4 = "task_baa139877a4d4fbfa601df50610262d5"   # World 9 Task 4: 4 world files + 1 task pdf, 2 criteria
T30 = "task_b66225e0cce148509c5d4c9b4773e554"  # World 9 Task 30: smallest, 2 files


def _row(tid):
    return next(json.loads(l) for l in DEV.read_text(encoding="utf-8").splitlines() if json.loads(l)["task_id"] == tid)


def test_tasks_prompt_then_one_block_per_file_in_order():
    [t] = apex.tasks(DEV, [T30])
    row = _row(T30)
    assert t["id"] == T30
    assert t["prompt"].startswith(row["prompt"] + "\n\n==== Attached files content: ====\n\n")
    heads = [t["prompt"].index(f"=== {f} ===\n") for f in row["context_files"]]
    assert heads == sorted(heads)
    m = t["metadata"]
    assert m["prompt_raw"] == row["prompt"] and list(m["attachment_chars"]) == row["context_files"]
    assert {k: m[k] for k in ("task_name", "world_id", "context_files", "rubric", "gold_output", "metadata")} == \
           {k: row[k] for k in ("task_name", "world_id", "context_files", "rubric", "gold_output", "metadata")}


def test_tasks_pdf_from_task_files_and_run_picks_this_loader():
    [t] = run.load_tasks(DEV, [T4], max_chars=10**7)  # the QBO register is over the default per-file cap
    assert "=== Whitfield_PostSettlement_Holdback_Memo.pdf ===\n--- page 1 ---" in t["prompt"]
    assert "=== qbo_journal_entry_register_2024.xlsx ===\n--- sheet" in t["prompt"]


def test_tasks_over_cap_dies_naming_task_and_file():
    with pytest.raises(SystemExit, match=f"task {T4}: attachment qbo_journal_entry_register_2024.xlsx"):
        apex.tasks(DEV, [T4])


def test_rubrics_in_order_nulls_for_absent_type_kept_as_metadata():
    rub = grade.load_rubrics(DEV)
    row = _row(T4)
    assert [c["id"] for c in rub[T4]] == [c["id"] for c in row["rubric"]]
    c = rub[T4][0]
    assert c["description"] == row["rubric"][0]["description"]
    assert c["weight"] is None and c["depends_on"] is None
    assert c["metadata"] == {"criterion_type": row["rubric"][0]["criterion_type"]}


def test_gold_is_gold_output_by_task_id():
    g = grade.load_gold(DEV)
    assert g[T4] == _row(T4)["gold_output"] and g[T30] == _row(T30)["gold_output"]


def test_outputs_one_model_last_line_wins(tmp_path):
    raw = tmp_path / "raw.jsonl"
    lines = [{"task_id": T4, "model": "a", "sample_index": 0, "response": "old"},
             {"task_id": T4, "model": "a", "sample_index": 0, "response": "new"},
             {"task_id": T4, "model": "a", "sample_index": 1, "response": "x"},
             {"task_id": T4, "model": "b", "sample_index": 0, "response": "other model"}]
    raw.write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")
    assert apex.outputs(raw, "a") == [{"task_id": T4, "run": 0, "output": "new"},
                                      {"task_id": T4, "run": 1, "output": "x"}]


def test_outputs_missing_response_dies(tmp_path):
    raw = tmp_path / "raw.jsonl"
    raw.write_text(json.dumps({"task_id": T4, "model": "a", "sample_index": 0, "response": None}) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no response"):
        apex.outputs(raw, "a")
