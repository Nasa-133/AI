import pytest

from business.contexts.governance.domain.pii import (
    TOKEN_RE,
    mask_text,
    mask_value,
    redact_text,
    unmask_text,
    unmask_value,
)


class Vault:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def token_for(self, kind: str, value: str) -> str:
        token = f"[{kind}-{abs(hash(value)) % 16**8:08x}]"
        self.values[token] = value
        return token

    def lookup(self, token: str) -> str | None:
        return self.values.get(token)


@pytest.mark.parametrize("pii", [
    "+998 90 123 45 67", "998901234567", "90-123-45-67", "(71) 200 00 00",
    "ali.valiyev@mail.uz", "32010785430027", "AA 1234567", "AB1234567", "8600 1234 5678 9012",
])
def test_detects_personal_data(pii: str) -> None:
    v = Vault()
    masked = mask_text(f"Mijoz: {pii}, iltimos bog‘laning.", v.token_for)
    assert pii not in masked and TOKEN_RE.search(masked), masked
    assert unmask_text(masked, v.lookup) == f"Mijoz: {pii}, iltimos bog‘laning."


@pytest.mark.parametrize("safe", [
    "Sof savdo 1 250 000,00 so‘m", "2026-01-31", "To‘lov 30 kun ichida", "TOS filiali",
    "Summa 1250000.00", "Buyurtma 12345", "900000000.00", "Summa 912345678.50 so‘m",
    "Tushum: 912345678,50", "12",
])
def test_business_numbers_are_not_masked(safe: str) -> None:
    assert mask_text(safe, Vault().token_for) == safe


def test_table_person_columns_and_roundtrip() -> None:
    v = Vault()
    result = {"columns": [{"name": "customer", "kind": "dimension"},
                          {"name": "net_sales", "kind": "metric"}],
              "rows": [["Valiyev Ali", "100.00"], ["Karimova Nodira", "90.00"], [None, "1.00"]],
              "notes": ["Tel: +998901234567"]}
    masked = mask_value(result, v.token_for, mask_people=True)
    assert "Valiyev" not in str(masked) and "+998" not in str(masked)
    assert masked["rows"][0][1] == "100.00" and masked["rows"][2][0] is None
    assert unmask_value(masked, v.lookup) == result
    assert mask_value(result, v.token_for, mask_people=False)["rows"][0][0] == "Valiyev Ali"


def test_answer_restores_only_known_tokens() -> None:
    v = Vault()
    token = v.token_for("SHAXS", "Valiyev Ali")
    assert unmask_text(f"Eng ko‘p: {token}; [SHAXS-deadbeef] noma’lum",
                       v.lookup) == "Eng ko‘p: Valiyev Ali; [SHAXS-deadbeef] noma’lum"


def test_redact_for_embeddings() -> None:
    assert redact_text("Tel +998 90 123 45 67, email a@b.uz") == "Tel [TEL], email [EMAIL]"


def test_bare_identifiers_in_cells_are_masked() -> None:
    v = Vault()
    for cell in ("32010785430027", "901234567", "8600123456789012"):
        assert mask_text(cell, v.token_for) != cell
