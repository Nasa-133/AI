from business.kernel.errors import BusinessError, ValidationFailed


class InvalidEmail(ValidationFailed):
    pass


class WeakPassword(ValidationFailed):
    pass


class InvalidTenant(ValidationFailed):
    pass


class InvalidBranchScope(ValidationFailed):
    pass


class MfaAlreadyEnabled(BusinessError):
    code = "MFA_ALREADY_ENABLED"


class MfaNotEnrolled(BusinessError):
    code = "MFA_NOT_ENROLLED"


class MfaSecretUnreadable(BusinessError):
    """Saqlangan 2FA siri joriy shifrlash kaliti bilan ochilmaydi (kalit almashgan)."""

    code = "MFA_RESET_REQUIRED"


class MfaCodeReused(BusinessError):
    code = "INVALID_MFA_CODE"


class Forbidden(BusinessError):
    code = "FORBIDDEN"


class LastOwner(BusinessError):
    code = "LAST_OWNER"


class InvitationInvalid(BusinessError):
    code = "INVITATION_INVALID"


class ResetTokenInvalid(BusinessError):
    code = "RESET_TOKEN_INVALID"
