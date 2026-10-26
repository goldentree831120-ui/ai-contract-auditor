from auditor.metrics import _prf, scores

CLASSES = ["reentrancy", "arithmetic"]


def test_prf_conventions():
    assert _prf(2, 1, 1) == {"tp": 2, "fp": 1, "fn": 1, "precision": 0.667, "recall": 0.667, "f1": 0.667}
    nothing = _prf(0, 0, 3)  # tool never predicts the class
    assert nothing["precision"] is None and nothing["recall"] == 0.0 and nothing["f1"] == 0.0


def test_scores_per_class_and_averages():
    gold = {("c1", "reentrancy"), ("c2", "arithmetic")}
    pred = {("c1", "reentrancy"), ("c3", "reentrancy")}
    s = scores(pred, gold, CLASSES)
    assert s["per_class"]["reentrancy"]["precision"] == 0.5
    assert s["per_class"]["arithmetic"]["f1"] == 0.0
    assert s["micro"] == {"tp": 1, "fp": 1, "fn": 1, "precision": 0.5, "recall": 0.5, "f1": 0.5}
    assert s["macro"]["f1"] == round((0.667 + 0.0) / 2, 3)


def test_function_level_is_stricter():
    gold = {("c1", "reentrancy", "withdraw")}
    pred = {("c1", "reentrancy", "deposit")}
    s = scores(pred, gold, CLASSES)
    assert s["micro"]["tp"] == 0 and s["micro"]["fp"] == 1


def test_committed_report_is_current():
    import subprocess
    import sys

    from auditor.dataset import REPO_ROOT

    r = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "evaluate.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
