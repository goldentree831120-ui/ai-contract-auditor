import importlib.util
import sys
import types

from auditor.dataset import REPO_ROOT

# Lets tests import scripts/*.py as `from scripts_path import build_site`.
pkg = types.ModuleType("scripts_path")
for name in ("build_site",):
    spec = importlib.util.spec_from_file_location(f"scripts_path.{name}", REPO_ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    setattr(pkg, name, mod)
sys.modules["scripts_path"] = pkg
