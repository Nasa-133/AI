"""Servislar va kontekstlar orasidagi import chegaralari (TZ 13.3, 13.4, 13.15 gate 1).

Har servis ichidagi qatlam qoidalari o‘sha servisning import-linter konfiguratsiyasida;
bu test esa servislararo va kontekstlararo qoidalarni butun repo bo‘ylab tekshiradi.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICES = {
    "business": ROOT / "services/business/src/business",
    "ai_runtime": ROOT / "services/ai_runtime/src/ai_runtime",
    "integration_runtime": ROOT / "services/integration_runtime/src/integration_runtime",
}
CONTEXTS_ROOT = SERVICES["business"] / "contexts"


def imported_modules(source: str) -> Iterator[str]:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def cross_service_violations(service: str, source: str) -> list[str]:
    others = set(SERVICES) - {service}
    return [m for m in imported_modules(source) if m.split(".")[0] in others]


def cross_context_violations(context: str, source: str) -> list[str]:
    """Boshqa kontekstdan faqat `business.contexts.<nom>.public` import qilinadi."""
    bad = []
    for module in imported_modules(source):
        parts = module.split(".")
        if parts[:2] != ["business", "contexts"] or len(parts) < 3 or parts[2] == context:
            continue
        if parts[3:] != ["public"]:
            bad.append(module)
    return bad


def python_files(path: Path) -> list[Path]:
    return sorted(path.rglob("*.py"))


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_services_do_not_import_each_other(service: str) -> None:
    violations = {
        str(f.relative_to(ROOT)): v
        for f in python_files(SERVICES[service])
        if (v := cross_service_violations(service, f.read_text(encoding="utf-8")))
    }
    assert not violations, f"Servislararo import taqiqlangan (kontrakt ishlating): {violations}"


def test_contexts_use_only_public_api_of_other_contexts() -> None:
    violations = {}
    for context_dir in (d for d in CONTEXTS_ROOT.iterdir() if d.is_dir() and d.name != "__pycache__"):
        for f in python_files(context_dir):
            if v := cross_context_violations(context_dir.name, f.read_text(encoding="utf-8")):
                violations[str(f.relative_to(ROOT))] = v
    assert not violations, f"Boshqa kontekstning ichki moduliga murojaat: {violations}"


PACKAGES = {"abo_messaging": ROOT / "packages/abo_messaging/src/abo_messaging"}


@pytest.mark.parametrize("package", sorted(PACKAGES))
def test_transport_packages_do_not_depend_on_services(package: str) -> None:
    """ADR 004: umumiy paket faqat transport; hech bir servisni bilmaydi."""
    violations = {
        str(f.relative_to(ROOT)): bad
        for f in python_files(PACKAGES[package])
        if (bad := [m for m in imported_modules(f.read_text(encoding="utf-8"))
                    if m.split(".")[0] in SERVICES])
    }
    assert not violations, f"Transport paketi servis kodini import qilmoqda: {violations}"


def test_domain_and_application_do_not_use_transport_package() -> None:
    """Messaging faqat adapter/platform/entrypoint qatlamida (xabar — infratuzilma)."""
    offenders = {}
    for layer in ("domain", "application", "ports"):
        for f in SERVICES["business"].glob(f"contexts/*/{layer}/**/*.py"):
            if any(m.startswith("abo_messaging") for m in
                   imported_modules(f.read_text(encoding="utf-8"))):
                offenders[str(f.relative_to(ROOT))] = layer
    assert not offenders, offenders


def test_no_shared_common_package() -> None:
    offenders = [p for p in (ROOT / "services").glob("*/src/*") if p.name in {"common", "shared"}]
    assert not offenders, f"Umumiy biznes paketi taqiqlangan (TZ 13.6): {offenders}"


# Tekshiruvchilarning o‘zi ishlashini isbotlovchi testlar (bo‘sh o‘tib ketmasligi uchun).
def test_checkers_detect_violations() -> None:
    assert cross_service_violations("ai_runtime", "from business.contexts import x") == [
        "business.contexts"
    ]
    assert cross_service_violations("business", "import integration_runtime.adapters") == [
        "integration_runtime.adapters"
    ]
    src = "from business.contexts.identity.adapters.sql import X\n" \
          "from business.contexts.identity.public import AuthContext\n" \
          "from business.contexts.analytics.domain import Y"
    assert cross_context_violations("analytics", src) == [
        "business.contexts.identity.adapters.sql"
    ]
