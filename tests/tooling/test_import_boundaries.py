import ast
from pathlib import Path


FORBIDDEN_IMPORTS = {
    ("scopes_tool_core", "scopes_tool_cli"),
    ("scopes_tool_core", "scopes_tool_webui"),
    ("scopes_tool_cli", "scopes_tool_webui"),
    ("scopes_tool_webui", "scopes_tool_cli"),
}


def test_package_import_boundaries():
    repo_root = Path(__file__).resolve().parents[2]
    package_roots = {
        "scopes_tool_core": repo_root / "src" / "scopes_tool_core",
        "scopes_tool_cli": repo_root / "src" / "scopes_tool_cli",
        "scopes_tool_webui": repo_root / "src" / "scopes_tool_webui",
    }
    violations = []

    for source_package, package_root in package_roots.items():
        for path in sorted(package_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            relative_path = path.relative_to(repo_root).as_posix()

            for node in ast.walk(tree):
                imported_packages = []
                if isinstance(node, ast.Import):
                    imported_packages = [
                        alias.name.split(".", 1)[0] for alias in node.names
                    ]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    if node.module is not None:
                        imported_packages = [node.module.split(".", 1)[0]]

                for imported_package in imported_packages:
                    if (source_package, imported_package) in FORBIDDEN_IMPORTS:
                        violations.append(
                            f"{relative_path}:{node.lineno}: "
                            f"{source_package} imports {imported_package}"
                        )

    assert violations == [], "Forbidden package imports:\n" + "\n".join(violations)
