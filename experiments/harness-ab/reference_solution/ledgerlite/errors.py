"""Error types and error codes for ledgerlite."""

E_INVALID_AMOUNT = "E_INVALID_AMOUNT"
E_UNKNOWN_CATEGORY = "E_UNKNOWN_CATEGORY"
E_NOT_FOUND = "E_NOT_FOUND"
E_BAD_FREQUENCY = "E_BAD_FREQUENCY"
E_BAD_MONTH = "E_BAD_MONTH"
E_BAD_DATE_RANGE = "E_BAD_DATE_RANGE"


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
