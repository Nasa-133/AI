"""tools/contracts/openapi_diff.py qoidalari uchun testlar."""

import copy
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "contracts"))

from openapi_diff import compare, main

Spec = dict[str, Any]


def spec(
    *,
    params: list[Spec] | None = None,
    body: Spec | None = None,
    body_required: bool = True,
    response: Spec | None = None,
    statuses: tuple[str, ...] = ("200",),
) -> Spec:
    op: Spec = {"responses": {}}
    if params is not None:
        op["parameters"] = params
    if body is not None:
        op["requestBody"] = {
            "required": body_required,
            "content": {"application/json": {"schema": body}},
        }
    for status in statuses:
        op["responses"][status] = {
            "description": "ok",
            "content": {"application/json": {"schema": response or {"type": "object"}}},
        }
    return {"openapi": "3.1.0", "paths": {"/items": {"post": op}}, "components": {"schemas": {}}}


def obj(props: dict[str, Spec], required: list[str] | None = None) -> Spec:
    return {"type": "object", "properties": props, "required": required or []}


STR: Spec = {"type": "string"}


def breaking(base: Spec, cur: Spec) -> list[str]:
    return compare(base, cur).breaking


def non_breaking(base: Spec, cur: Spec) -> list[str]:
    return compare(base, cur).non_breaking


def test_identical_specs_have_no_findings() -> None:
    s = spec(response=obj({"id": STR}, ["id"]))
    report = compare(s, copy.deepcopy(s))
    assert report.breaking == [] and report.non_breaking == []


def test_removed_operation_is_breaking_new_one_is_not() -> None:
    base = spec()
    cur = copy.deepcopy(base)
    cur["paths"]["/other"] = cur["paths"].pop("/items")
    assert any("POST /items: operatsiya o‘chirildi" in m for m in breaking(base, cur))
    assert any("POST /other: yangi operatsiya" in m for m in non_breaking(base, cur))


def test_removed_2xx_status_is_breaking_non_2xx_is_not() -> None:
    base = spec(statuses=("200", "422"))
    assert breaking(base, spec(statuses=("201", "422")))
    only_4xx_removed = spec(statuses=("200",))
    assert breaking(base, only_4xx_removed) == []
    assert non_breaking(base, only_4xx_removed)


def test_response_property_removed_is_breaking_added_is_not() -> None:
    base = spec(response=obj({"id": STR, "name": STR}, ["id", "name"]))
    assert breaking(base, spec(response=obj({"id": STR}, ["id"])))
    added = spec(response=obj({"id": STR, "name": STR, "x": STR}, ["id", "name"]))
    assert breaking(base, added) == [] and non_breaking(base, added)


def test_response_required_becoming_optional_is_breaking() -> None:
    base = spec(response=obj({"id": STR}, ["id"]))
    assert breaking(base, spec(response=obj({"id": STR}, [])))


def test_property_type_change_is_breaking() -> None:
    base = spec(response=obj({"n": {"type": "integer"}}, ["n"]))
    assert breaking(base, spec(response=obj({"n": STR}, ["n"])))
    base_req = spec(body=obj({"n": {"type": "integer"}}, ["n"]))
    assert breaking(base_req, spec(body=obj({"n": STR}, ["n"])))


def test_nullability_rules_depend_on_direction() -> None:
    nullable: Spec = {"anyOf": [STR, {"type": "null"}]}
    # Javob kengaysa (null qaytishi mumkin) — breaking; torayganda — yo‘q.
    assert breaking(spec(response=obj({"a": STR}, ["a"])),
                    spec(response=obj({"a": nullable}, ["a"])))
    assert breaking(spec(response=obj({"a": nullable}, ["a"])),
                    spec(response=obj({"a": STR}, ["a"]))) == []
    # So‘rov kengaysa — breaking emas; torayganda — breaking.
    assert breaking(spec(body=obj({"a": STR}, ["a"])),
                    spec(body=obj({"a": nullable}, ["a"]))) == []
    assert breaking(spec(body=obj({"a": nullable}, ["a"])),
                    spec(body=obj({"a": STR}, ["a"])))


def test_enum_rules() -> None:
    e2: Spec = {"type": "string", "enum": ["a", "b"]}
    e3: Spec = {"type": "string", "enum": ["a", "b", "c"]}
    e1: Spec = {"type": "string", "enum": ["a"]}
    # So‘rov: o‘chirish breaking, qo‘shish emas.
    assert breaking(spec(body=obj({"k": e2}, ["k"])), spec(body=obj({"k": e1}, ["k"])))
    assert breaking(spec(body=obj({"k": e2}, ["k"])), spec(body=obj({"k": e3}, ["k"]))) == []
    # Javob: qo‘shish breaking (qat’iy klientlar), o‘chirish emas.
    assert breaking(spec(response=obj({"k": e2}, ["k"])), spec(response=obj({"k": e3}, ["k"])))
    assert breaking(spec(response=obj({"k": e2}, ["k"])),
                    spec(response=obj({"k": e1}, ["k"]))) == []


def test_new_required_request_field_is_breaking_optional_is_not() -> None:
    base = spec(body=obj({"a": STR}, ["a"]))
    assert breaking(base, spec(body=obj({"a": STR, "b": STR}, ["a", "b"])))
    assert breaking(base, spec(body=obj({"a": STR, "b": STR}, ["a"]))) == []


def test_request_field_becoming_required_is_breaking() -> None:
    base = spec(body=obj({"a": STR, "b": STR}, ["a"]))
    assert breaking(base, spec(body=obj({"a": STR, "b": STR}, ["a", "b"])))


def test_new_required_body_is_breaking() -> None:
    assert breaking(spec(), spec(body=obj({"a": STR})))
    assert breaking(spec(), spec(body=obj({"a": STR}), body_required=False)) == []


def test_parameter_rules() -> None:
    q: Spec = {"in": "query", "name": "q", "required": False, "schema": STR}
    base = spec(params=[q])
    assert breaking(base, spec(params=[]))  # o‘chirildi
    assert breaking(base, spec(params=[{**q, "required": True}]))  # majburiy bo‘ldi
    new_req: Spec = {"in": "query", "name": "p", "required": True, "schema": STR}
    assert breaking(base, spec(params=[q, new_req]))
    new_opt: Spec = {"in": "query", "name": "p", "required": False, "schema": STR}
    assert breaking(base, spec(params=[q, new_opt])) == []


def test_refs_are_resolved_and_recursive_schemas_terminate() -> None:
    def with_ref(props: dict[str, Spec]) -> Spec:
        s = spec(response={"$ref": "#/components/schemas/Node"})
        s["components"]["schemas"]["Node"] = obj(
            {**props, "child": {"$ref": "#/components/schemas/Node"}}, list(props)
        )
        return s

    base = with_ref({"id": STR, "name": STR})
    assert any("name" in m for m in breaking(base, with_ref({"id": STR})))
    assert breaking(base, copy.deepcopy(base)) == []


def test_metadata_only_change_is_non_breaking() -> None:
    base = spec()
    cur = copy.deepcopy(base)
    cur["paths"]["/items"]["post"]["summary"] = "Yangi tavsif"
    report = compare(base, cur)
    assert report.breaking == [] and report.non_breaking


def test_cli_exit_codes_and_markers(tmp_path: Path, capsys: Any) -> None:
    import json

    base = spec(response=obj({"id": STR, "name": STR}, ["id", "name"]))
    cur = spec(response=obj({"id": STR, "name": STR, "x": STR}, ["id", "name"]))
    (tmp_path / "b.json").write_text(json.dumps(base))
    (tmp_path / "c.json").write_text(json.dumps(cur))
    assert main(["x", str(tmp_path / "b.json"), str(tmp_path / "c.json")]) == 0
    assert "NON_BREAKING:" in capsys.readouterr().out
    assert main(["x", str(tmp_path / "c.json"), str(tmp_path / "b.json")]) == 1
    assert "BREAKING:" in capsys.readouterr().out
