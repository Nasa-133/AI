from business.kernel.errors import BusinessError, ValidationFailed


class InvalidEmail(ValidationFailed):
    pass


class WeakPassword(ValidationFailed):
    pass


class InvalidTenant(ValidationFailed):
    pass


class MfaAlreadyEnabled(BusinessError):
    code = "MFA_ALREADY_ENABLED"


class MfaNotEnrolled(BusinessError):
    code = "MFA_NOT_ENROLLED"
