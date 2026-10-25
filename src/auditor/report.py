"""Contract-level summaries shared by tool runs (precision/recall/F1 come in M5)."""

from __future__ import annotations

from auditor.dataset import load_taxonomy


def predicted_classes(result: dict) -> set[str]:
    return {f["class"] for f in result.get("findings", []) if f.get("class")}


def contract_level(entries: list[dict], results: dict[str, dict]) -> dict:
    """How often a tool flags vulnerable vs clean contracts, overall and per class."""
    vuln = [e for e in entries if e["label"] == "vulnerable"]
    clean = [e for e in entries if e["label"] == "clean"]
    per_class = {}
    for c in load_taxonomy()["classes"]:
        has = [e for e in entries if c in e["classes"]]
        hasnt = [e for e in entries if c not in e["classes"]]
        per_class[c] = {
            "contracts_with_class": len(has),
            "flagged_with_this_class": sum(c in predicted_classes(results[e["id"]]) for e in has),
            "flagged_without_having_it": sum(c in predicted_classes(results[e["id"]]) for e in hasnt),
        }
    return {
        "vulnerable_contracts": len(vuln),
        "vulnerable_flagged_any_class": sum(bool(predicted_classes(results[e["id"]])) for e in vuln),
        "clean_contracts": len(clean),
        "clean_flagged_any_class": sum(bool(predicted_classes(results[e["id"]])) for e in clean),
        "per_class": per_class,
    }


def per_class_table(per_class: dict, note: dict[str, str] | None = None) -> list[str]:
    rows = ["| class | contracts with class | flagged, has class | flagged, does not have class |",
            "|---|---|---|---|"]
    for c, v in per_class.items():
        rows.append(f"| {c}{(note or {}).get(c, '')} | {v['contracts_with_class']} | "
                    f"{v['flagged_with_this_class']} | {v['flagged_without_having_it']} |")
    return rows
