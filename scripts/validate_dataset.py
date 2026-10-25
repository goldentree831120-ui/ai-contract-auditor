"""Validate dataset/ and print a summary. Exit code 1 if any problem is found."""

import json
import sys

from auditor.dataset import summary, validate

errors = validate()
for e in errors:
    print("ERROR", e)
print(json.dumps(summary(), indent=2))
print("validation:", "FAILED" if errors else "passed")
sys.exit(1 if errors else 0)
