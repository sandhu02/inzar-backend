"""AST-based tests enforcing architectural layer boundaries and cross-module import rules."""

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent / "app"


def get_all_python_files(directory: Path) -> list[Path]:
    return list(directory.rglob("*.py"))


def parse_imports(file_path: Path) -> tuple[list[str], list[str]]:
    """Return imported module paths and names from AST."""
    with open(file_path, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=str(file_path))
        except SyntaxError:
            return [], []

    modules = []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append(node.module)
                for alias in node.names:
                    names.append(f"{node.module}.{alias.name}")
    return modules, names


def test_routers_do_not_import_repositories():
    """Routers must only call services, never import repositories directly."""
    modules_dir = APP_DIR / "modules"
    if not modules_dir.exists():
        return

    for router_file in modules_dir.rglob("router*.py"):
        modules, names = parse_imports(router_file)
        all_imported = modules + names
        for imp in all_imported:
            assert "repository" not in imp, (
                f"Layer violation in {router_file.name}: Routers must not import repositories ({imp})"
            )


def test_cross_module_repository_isolation():
    """A module must never import another module's repository."""
    modules_dir = APP_DIR / "modules"
    if not modules_dir.exists():
        return

    for py_file in modules_dir.rglob("*.py"):
        # Determine current module name
        relative = py_file.relative_to(modules_dir)
        current_module = relative.parts[0] if len(relative.parts) > 1 else None
        if not current_module:
            continue

        modules, names = parse_imports(py_file)
        all_imported = modules + names

        for imp in all_imported:
            if "app.modules." in imp and "repository" in imp:
                parts = imp.split(".")
                idx = parts.index("modules")
                if len(parts) > idx + 1:
                    target_module = parts[idx + 1]
                    if target_module != current_module:
                        raise AssertionError(
                            f"Cross-module isolation violation in {py_file}: "
                            f"Module '{current_module}' must not import repository from '{target_module}' ({imp})"
                        )


def test_repositories_do_not_import_services_or_routers():
    """Repositories must not depend on service or router layers."""
    modules_dir = APP_DIR / "modules"
    if not modules_dir.exists():
        return

    for repo_file in modules_dir.rglob("repository*.py"):
        modules, names = parse_imports(repo_file)
        all_imported = modules + names
        for imp in all_imported:
            assert "service" not in imp.split("."), (
                f"Layer violation in {repo_file.name}: Repositories must not import services ({imp})"
            )
            assert "router" not in imp.split("."), (
                f"Layer violation in {repo_file.name}: Repositories must not import routers ({imp})"
            )


def test_routers_do_not_import_sqlalchemy_query_builders():
    """Routers must contain no direct database queries or query builder statements."""
    modules_dir = APP_DIR / "modules"
    if not modules_dir.exists():
        return

    forbidden_sqlalchemy_functions = ["select", "insert", "update", "delete", "text"]
    for router_file in modules_dir.rglob("router*.py"):
        _, names = parse_imports(router_file)
        for imp in names:
            for forbidden in forbidden_sqlalchemy_functions:
                assert imp != f"sqlalchemy.{forbidden}", (
                    f"Architecture violation: {router_file.name} directly imports sqlalchemy.{forbidden}. "
                    "All database queries must reside in the repository layer."
                )
