"""Error types and error codes for ledgerlite."""

E_INVALID_AMOUNT = "E_INVALID_AMOUNT"
E_UNKNOWN_CATEGORY = "E_UNKNOWN_CATEGORY"
E_NOT_FOUND = "E_NOT_FOUND"
E_FISCAL_PERIOD = "E_FISCAL_PERIOD"
E_EXPORT_FORMAT = "E_EXPORT_FORMAT"
E_SPLIT_WEIGHTS = "E_SPLIT_WEIGHTS"
E_EXPORT_EXISTS = "E_EXPORT_EXISTS"
E_RETENTION_PERIODS = "E_RETENTION_PERIODS"


class LedgerError(Exception):
    """Raised for all domain-level errors in ledgerlite.

    Attributes:
        code: one of the E_* constants identifying the error kind.
        message: a short human-readable description.
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
