from business.kernel.errors import BusinessError


class InvalidCredentials(BusinessError):
    code = "INVALID_CREDENTIALS"


class AccountLocked(BusinessError):
    code = "ACCOUNT_LOCKED"
    retryable = True


class EmailTaken(BusinessError):
    code = "EMAIL_TAKEN"


class Unauthenticated(BusinessError):
    code = "UNAUTHENTICATED"


class MfaRequired(BusinessError):
    code = "MFA_REQUIRED"


class InvalidMfaCode(BusinessError):
    code = "INVALID_MFA_CODE"


class NotAMember(BusinessError):
    """Obyekt mavjudligini oshkor qilmaslik uchun 404 sifatida qaytariladi."""

    code = "NOT_FOUND"
