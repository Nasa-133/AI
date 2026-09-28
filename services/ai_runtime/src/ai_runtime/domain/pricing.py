"""Model narxi konfiguratsiyadan (TZ 19: narx kodga tikilmaydi) — 1 mln token uchun."""

from dataclasses import dataclass
from decimal import Decimal

_MICRO = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class Pricing:
    input_per_1m: Decimal = Decimal("0")
    output_per_1m: Decimal = Decimal("0")
    currency: str = "USD"

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        total = (Decimal(input_tokens) * self.input_per_1m
                 + Decimal(output_tokens) * self.output_per_1m) / Decimal(1_000_000)
        return total.quantize(_MICRO)
