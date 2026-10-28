import json
import re

from scripts_path import build_site  # noqa: F401  (see conftest)


def test_site_builds_with_embedded_data(tmp_path):
    data = build_site.collect()
    assert len(data["contracts"]) == 49 and "slither" in data["preds"] and "llm_only" in data["preds"]
    html = build_site.render(data)
    assert "__DATA__" not in html and "<script src" not in html  # self-contained
    blob = re.search(r"const D = (\{.*?\});\n", html, re.S).group(1)
    assert json.loads(blob.replace("<\\/", "</"))["base"][0] == "slither"
