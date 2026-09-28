"""S02: filial doirasi — so‘rov filtri, identity qoidasi, dashboard widget tekshiruvi."""

from datetime import date

import pytest

from business.contexts.analytics.application.queries import BranchForbidden, apply_branch_scope
from business.contexts.analytics.domain.metrics import Dimension
from business.contexts.analytics.domain.query import Filters, Period, QuerySpec
from business.contexts.dashboards.domain.access import within_branch_scope
from business.contexts.identity.domain.errors import Forbidden, InvalidBranchScope
from business.contexts.identity.domain.model import Role, normalize_branch_scope

SPEC = QuerySpec(("net_sales",), Period(date(2026, 1, 1), date(2026, 1, 31)),
                 (Dimension.BRANCH,))


def test_unscoped_user_is_unchanged() -> None:
    assert apply_branch_scope(SPEC, None) == (SPEC, None)


def test_general_query_is_narrowed_with_note() -> None:
    spec, note = apply_branch_scope(SPEC, ("BUX", "NAM"))
    assert spec.filters.branch_codes == ("BUX", "NAM")
    assert note == "Faqat ruxsat etilgan filiallar: BUX, NAM."


def test_subset_filter_is_kept_and_forbidden_branch_rejected() -> None:
    narrowed = QuerySpec(SPEC.metric_ids, SPEC.period, filters=Filters(branch_codes=("NAM",)))
    spec, note = apply_branch_scope(narrowed, ("BUX", "NAM"))
    assert spec.filters.branch_codes == ("NAM",) and note is not None
    wide = QuerySpec(SPEC.metric_ids, SPEC.period, filters=Filters(branch_codes=("NAM", "TOS")))
    with pytest.raises(BranchForbidden, match="TOS"):
        apply_branch_scope(wide, ("BUX", "NAM"))
    with pytest.raises(BranchForbidden):
        apply_branch_scope(SPEC, ())


def test_scope_only_for_analyst_and_viewer() -> None:
    assert normalize_branch_scope(Role.ANALYST, [" BUX", "BUX", "NAM "]) == ("BUX", "NAM")
    assert normalize_branch_scope(Role.OWNER, None) is None
    with pytest.raises(Forbidden):
        normalize_branch_scope(Role.ADMIN, ["BUX"])
    with pytest.raises(InvalidBranchScope):
        normalize_branch_scope(Role.VIEWER, [" "])


def test_widget_visible_only_when_limited_to_scope() -> None:
    assert within_branch_scope(None, None)
    assert within_branch_scope(("BUX",), ("BUX",))
    assert not within_branch_scope(("BUX",), None)  # barcha filiallar natijasi
    assert not within_branch_scope(("BUX",), ("BUX", "TOS"))


def test_counted_notes_are_merged_across_rows() -> None:
    from business.contexts.analytics.application.queries import merge_notes

    notes = ["33 ta savdo satrida tannarx yo‘q — foyda yuqoriroq", "Davr hali tugamagan",
             "17 ta savdo satrida tannarx yo‘q — foyda yuqoriroq", "Davr hali tugamagan"]
    assert merge_notes(notes) == ["50 ta savdo satrida tannarx yo‘q — foyda yuqoriroq",
                                  "Davr hali tugamagan"]
