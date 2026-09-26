"""Barcha kontekstlar uchun umumiy xato turi. Framework’ga bog‘lanmagan."""


class BusinessError(Exception):
    """Foydalanuvchiga tushunarli, kutilgan xato.

    `code` — kontraktdagi barqaror identifikator; HTTP statusga moslash
    entrypoint qatlamida bajariladi.
    """

    code: str = "BUSINESS_ERROR"
    retryable: bool = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationFailed(BusinessError):
    code = "VALIDATION_ERROR"
