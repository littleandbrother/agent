from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests.helpers import REPO


SOURCE = REPO / "packages" / "python" / "bfworld" / "src" / "bfworld"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class DependencyBoundaryTests(unittest.TestCase):
    def test_no_new_code_imports_legacy_lhsai(self) -> None:
        offenders = []
        for path in SOURCE.rglob("*.py"):
            if any(module == "lhsai" or module.startswith("lhsai.") for module in imported_modules(path)):
                offenders.append(str(path.relative_to(REPO)))
        self.assertEqual(offenders, [])

    def test_constitutional_layers_do_not_import_outer_layers(self) -> None:
        rules = {
            "contracts": ("bfworld.runtime", "bfworld.worlds", "bfworld.application", "bfworld.studio", "bfworld.agent", "bfworld.verification"),
            "kernel": ("bfworld.runtime", "bfworld.worlds", "bfworld.application", "bfworld.studio", "bfworld.agent", "bfworld.verification"),
            "worlds": ("bfworld.runtime", "bfworld.bundle", "bfworld.application", "bfworld.studio", "bfworld.agent", "bfworld.verification"),
            "studio": ("bfworld.runtime", "bfworld.worlds", "bfworld.application", "bfworld.agent", "bfworld.verification"),
            "agent": ("bfworld.runtime", "bfworld.worlds", "bfworld.application", "bfworld.studio", "bfworld.verification"),
            "verification": ("bfworld.worlds", "bfworld.application", "bfworld.studio", "bfworld.agent"),
        }
        offenders = []
        for package, forbidden in rules.items():
            for path in (SOURCE / package).rglob("*.py"):
                for module in imported_modules(path):
                    if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden):
                        offenders.append(f"{path.relative_to(REPO)} -> {module}")
        self.assertEqual(offenders, [])

    def test_apps_contain_no_python_scientific_logic(self) -> None:
        app_root = REPO / "apps"
        self.assertEqual(list(app_root.rglob("*.py")), [])


if __name__ == "__main__":
    unittest.main()

