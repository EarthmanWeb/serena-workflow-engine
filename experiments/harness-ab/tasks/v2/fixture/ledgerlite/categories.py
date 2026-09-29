"""Fixed category set for ledgerlite transactions."""

ALLOWED_CATEGORIES = frozenset(
    {
        "groceries",
        "rent",
        "utilities",
        "transport",
        "dining",
        "salary",
        "other",
    }
)
