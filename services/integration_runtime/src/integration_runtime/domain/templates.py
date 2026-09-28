"""Tanish manba formatlari uchun mapping shablonlari (SchemaDiscovered takliflari).

Shablon faqat sarlavhada aynan mavjud ustunlarni taklif qiladi; noma’lum ustun hech qachon
taxmin qilinmaydi. `match_score` = sarlavhada topilgan shablon ustunlari / shablon ustunlari.
"""

from dataclasses import dataclass

from .canonical import ENTITY_FIELDS
from .mapping import MappingItem, Transform

T = Transform

_SALES_STATUS = {"tasdiqlangan": "confirmed", "qoralama": "draft", "bekor qilingan": "cancelled"}
_MOVEMENT_TYPES = {
    "kirim": "receipt",
    "sotuv": "sale",
    "qaytarish": "return",
    "ko‘chirish_kirim": "transfer_in",
    "ko‘chirish_chiqim": "transfer_out",
    "tuzatish": "adjustment",
}


@dataclass(frozen=True, slots=True)
class Template:
    entity: str
    source_name: str
    # canonical maydon → (manba ustuni | None, transform, const qiymati)
    fields: dict[str, tuple[str | None, Transform, str | None]]
    status_map: dict[str, str]

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(c for c, _, _ in self.fields.values() if c is not None)


TEMPLATES: tuple[Template, ...] = (
    Template(
        entity="sales.order_line",
        source_name="sotuvlar.csv",
        fields={
            "source_id": ("Hujjat ID", T.TEXT, None),
            "source_revision": (None, T.TEXT, None),
            "document_number": ("Hujjat №", T.TEXT, None),
            "occurred_at": ("Sana", T.DATETIME_TZ, None),
            "branch_code": ("Filial kodi", T.TEXT, None),
            "branch_name": ("Filial", T.TEXT, None),
            "product_code": ("Mahsulot kodi", T.TEXT, None),
            "product_name": ("Mahsulot", T.TEXT, None),
            "customer_code": ("Mijoz kodi", T.TEXT, None),
            "customer_name": ("Mijoz", T.TEXT, None),
            "quantity": ("Miqdor", T.DECIMAL, None),
            "unit_price": ("Narx", T.DECIMAL, None),
            "gross_amount": ("Summa", T.DECIMAL, None),
            "discount_amount": ("Chegirma", T.DECIMAL, None),
            "discount_already_deducted": (None, T.CONST, "false"),
            "vat_amount": ("QQS", T.DECIMAL, None),
            "amount_includes_vat": (None, T.CONST, "false"),
            "currency": ("Valyuta", T.TEXT, None),
            "status": ("Holat", T.STATUS_MAP, None),
            "cost_amount": ("Tannarx", T.DECIMAL_OR_NULL, None),
        },
        status_map=_SALES_STATUS,
    ),
    Template(
        entity="sales.return",
        source_name="qaytarishlar.csv",
        fields={
            "source_id": ("Qaytarish ID", T.TEXT, None),
            "source_revision": (None, T.TEXT, None),
            "original_order_source_id": ("Asl hujjat ID", T.TEXT, None),
            "occurred_at": ("Sana", T.DATETIME_TZ, None),
            "branch_code": ("Filial kodi", T.TEXT, None),
            "product_code": ("Mahsulot kodi", T.TEXT, None),
            "customer_code": ("Mijoz kodi", T.TEXT, None),
            "quantity": ("Miqdor", T.DECIMAL, None),
            "amount": ("Summa", T.DECIMAL, None),
            "vat_amount": ("QQS", T.DECIMAL, None),
            "amount_includes_vat": (None, T.CONST, "false"),
            "currency": ("Valyuta", T.TEXT, None),
            "cost_amount": ("Tannarx", T.DECIMAL_OR_NULL, None),
            "status": ("Holat", T.STATUS_MAP, None),
        },
        status_map=_SALES_STATUS,
    ),
    Template(
        entity="inventory.movement",
        source_name="ombor_harakatlari.csv",
        fields={
            "source_id": ("Harakat ID", T.TEXT, None),
            "occurred_at": ("Sana", T.DATETIME_TZ, None),
            "warehouse_code": ("Ombor kodi", T.TEXT, None),
            "branch_code": ("Filial kodi", T.TEXT, None),
            "product_code": ("Mahsulot kodi", T.TEXT, None),
            "quantity_delta": ("Miqdor", T.DECIMAL, None),
            "movement_type": ("Turi", T.STATUS_MAP, None),
            "unit_cost": ("Birlik tannarxi", T.DECIMAL_OR_NULL, None),
            "currency": ("Valyuta", T.TEXT, None),
        },
        status_map=_MOVEMENT_TYPES,
    ),
    Template(
        entity="finance.receivable",
        source_name="debitorlik.csv",
        fields={
            "source_id": ("Hujjat ID", T.TEXT, None),
            "source_revision": (None, T.TEXT, None),
            "customer_code": ("Mijoz kodi", T.TEXT, None),
            "customer_name": ("Mijoz", T.TEXT, None),
            "document_number": ("Hujjat №", T.TEXT, None),
            "issued_on": ("Sana", T.DATE, None),
            "due_on": ("To‘lov muddati", T.DATE, None),
            "amount": ("Summa", T.DECIMAL, None),
            "paid_amount": ("To‘langan", T.DECIMAL, None),
            "currency": ("Valyuta", T.TEXT, None),
            "branch_code": ("Filial kodi", T.TEXT, None),
        },
        status_map={},
    ),
)

# ERP REST API (erp_api connector, tools/fake_erp shartnomasi): inglizcha ERP maydonlari.
_ERP_STATE = {"posted": "confirmed", "draft": "draft", "cancelled": "cancelled"}
_ERP_KIND = {k: k for k in ("receipt", "sale", "return", "transfer_in", "transfer_out",
                            "adjustment")}

ERP_TEMPLATES: tuple[Template, ...] = (
    Template(
        entity="sales.order_line",
        source_name="erp://sales-invoice-lines",
        fields={
            "source_id": ("line_id", T.TEXT, None),
            "source_revision": ("updated_at", T.TEXT, None),
            "document_number": ("invoice_no", T.TEXT, None),
            "occurred_at": ("posted_at", T.DATETIME_TZ, None),
            "branch_code": ("branch_code", T.TEXT, None),
            "branch_name": ("branch_name", T.TEXT, None),
            "product_code": ("item_code", T.TEXT, None),
            "product_name": ("item_name", T.TEXT, None),
            "customer_code": ("customer_code", T.TEXT, None),
            "customer_name": ("customer_name", T.TEXT, None),
            "quantity": ("qty", T.DECIMAL, None),
            "unit_price": ("price", T.DECIMAL, None),
            "gross_amount": ("amount", T.DECIMAL, None),
            "discount_amount": ("discount", T.DECIMAL, None),
            "discount_already_deducted": (None, T.CONST, "false"),
            "vat_amount": ("vat", T.DECIMAL, None),
            "amount_includes_vat": (None, T.CONST, "false"),
            "currency": ("currency", T.TEXT, None),
            "status": ("state", T.STATUS_MAP, None),
            "cost_amount": ("cost", T.DECIMAL_OR_NULL, None),
        },
        status_map=_ERP_STATE,
    ),
    Template(
        entity="sales.return",
        source_name="erp://sales-returns",
        fields={
            "source_id": ("return_id", T.TEXT, None),
            "source_revision": ("updated_at", T.TEXT, None),
            "original_order_source_id": ("invoice_line_id", T.TEXT, None),
            "occurred_at": ("posted_at", T.DATETIME_TZ, None),
            "branch_code": ("branch_code", T.TEXT, None),
            "product_code": ("item_code", T.TEXT, None),
            "customer_code": ("customer_code", T.TEXT, None),
            "quantity": ("qty", T.DECIMAL, None),
            "amount": ("amount", T.DECIMAL, None),
            "vat_amount": ("vat", T.DECIMAL, None),
            "amount_includes_vat": (None, T.CONST, "false"),
            "currency": ("currency", T.TEXT, None),
            "cost_amount": ("cost", T.DECIMAL_OR_NULL, None),
            "status": ("state", T.STATUS_MAP, None),
        },
        status_map=_ERP_STATE,
    ),
    Template(
        entity="inventory.movement",
        source_name="erp://stock-movements",
        fields={
            "source_id": ("movement_id", T.TEXT, None),
            "occurred_at": ("moved_at", T.DATETIME_TZ, None),
            "warehouse_code": ("warehouse_code", T.TEXT, None),
            "branch_code": ("branch_code", T.TEXT, None),
            "product_code": ("item_code", T.TEXT, None),
            "quantity_delta": ("qty", T.DECIMAL, None),
            "movement_type": ("kind", T.STATUS_MAP, None),
            "unit_cost": ("unit_cost", T.DECIMAL_OR_NULL, None),
            "currency": ("currency", T.TEXT, None),
        },
        status_map=_ERP_KIND,
    ),
    Template(
        entity="finance.receivable",
        source_name="erp://receivables",
        fields={
            "source_id": ("doc_id", T.TEXT, None),
            "source_revision": ("updated_at", T.TEXT, None),
            "customer_code": ("customer_code", T.TEXT, None),
            "customer_name": ("customer_name", T.TEXT, None),
            "document_number": ("invoice_no", T.TEXT, None),
            "issued_on": ("doc_date", T.DATE, None),
            "due_on": ("due_date", T.DATE, None),
            "amount": ("amount", T.DECIMAL, None),
            "paid_amount": ("paid", T.DECIMAL, None),
            "currency": ("currency", T.TEXT, None),
            "branch_code": ("branch_code", T.TEXT, None),
        },
        status_map={},
    ),
)
# CRM REST API (crm_api connector, tools/fake_crm shartnomasi).
CRM_TEMPLATES: tuple[Template, ...] = (
    Template(
        entity="crm.deal",
        source_name="crm://deals",
        fields={
            "source_id": ("deal_id", T.TEXT, None),
            "source_revision": ("updated_at", T.TEXT, None),
            "deal_number": ("deal_no", T.TEXT, None),
            "customer_code": ("client_code", T.TEXT, None),
            "customer_name": ("client_name", T.TEXT, None),
            "branch_code": ("branch", T.TEXT, None),
            "stage": ("stage", T.TEXT, None),
            "status": ("state", T.STATUS_MAP, None),
            "amount": ("amount", T.DECIMAL, None),
            "currency": ("currency", T.TEXT, None),
            "created_at": ("created_at", T.DATETIME_TZ, None),
            "closed_at": ("closed_at", T.DATETIME_TZ, None),
            "channel": ("lead_source", T.TEXT, None),
        },
        status_map={"open": "open", "won": "won", "lost": "lost"},
    ),
)

TEMPLATES_BY_ENTITY = {t.entity: t for t in TEMPLATES}  # CSV shablonlari (fayl importi)
TEMPLATES = TEMPLATES + ERP_TEMPLATES + CRM_TEMPLATES


@dataclass(frozen=True, slots=True)
class Suggestion:
    entity: str
    match_score: float
    mapping: tuple[MappingItem, ...]
    unmapped_required_fields: tuple[str, ...]
    status_map: dict[str, str]


def suggest(columns: list[str]) -> list[Suggestion]:
    """Sarlavhaga mos shablonlar (score > 0), eng mosi birinchi."""
    present = {c.strip() for c in columns}
    suggestions: list[Suggestion] = []
    for template in TEMPLATES:
        matched = [c for c in template.columns if c in present]
        score = len(matched) / len(template.columns)
        if score == 0:
            continue
        specs = {f.name: f for f in ENTITY_FIELDS[template.entity]}
        items: list[MappingItem] = []
        unmapped: list[str] = []
        for field_name, (column, transform, constant) in template.fields.items():
            if column is not None and column not in present:
                # Ustun topilmadi: taxmin qilinmaydi, foydalanuvchi o‘zi tanlaydi.
                items.append(MappingItem(field_name, None, transform, None))
                if not specs[field_name].nullable:
                    unmapped.append(field_name)
                continue
            items.append(MappingItem(field_name, column, transform, constant))
        suggestions.append(Suggestion(template.entity, round(score, 4), tuple(items),
                                      tuple(unmapped), dict(template.status_map)))
    return sorted(suggestions, key=lambda s: s.match_score, reverse=True)
