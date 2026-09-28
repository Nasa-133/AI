"""Deterministik feature-hashing embedding (fake provider, lokal va testlar uchun).

So‘z va harf trigrammalari hash’lanadi: bir xil so‘zli matnlar yaqin, kalit tashqi
xizmat talab qilinmaydi. Sifati OpenAI embedding’iga teng emas — faqat pipeline’ni sinash uchun.
"""

import hashlib
import math
import re

_APOSTROPHES = str.maketrans({c: "'" for c in "ʻʼ‘’`´"})
_WORD = re.compile(r"[\w']+", re.UNICODE)


def _bucket(feature: str, dims: int) -> tuple[int, float]:
    h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
    return h % dims, (1.0 if (h >> 63) & 1 else -1.0)


class HashEmbedder:
    def __init__(self, dimensions: int = 256) -> None:
        self._dims = dimensions

    @property
    def model(self) -> str:
        return f"fake-hash-{self._dims}"

    @property
    def dimensions(self) -> int:
        return self._dims

    def vector(self, text: str) -> list[float]:
        vec = [0.0] * self._dims
        for word in _WORD.findall(text.lower().translate(_APOSTROPHES)):
            index, sign = _bucket("w:" + word, self._dims)
            vec[index] += sign
            padded = f"#{word}#"
            for i in range(len(padded) - 2):
                index, sign = _bucket("t:" + padded[i:i + 3], self._dims)
                vec[index] += 0.5 * sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            # Nol vektor kosinusda NaN beradi — bo‘sh matn uchun barqaror birlik vektor.
            vec[0] = 1.0
            return vec
        return [round(v / norm, 6) for v in vec]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vector(t) for t in texts]
