"""Identity kontekstining boshqa kontekstlar uchun ochiq kontrakti.

Boshqa kontekstlar faqat shu moduldan import qiladi (tests/architecture tekshiradi).
"""

from .application.dto import AuthContext
from .domain.model import Role

__all__ = ["AuthContext", "Role"]
