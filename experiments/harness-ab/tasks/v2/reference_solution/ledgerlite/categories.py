"""Fixed category set for ledgerlite transactions, plus input aliases."""

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

# Aliases accepted wherever a category is taken as input. Exports and all
# internal storage always use the canonical (right-hand side) name.
CATEGORY_ALIASES = {
    "food": "groceries",
    "car": "transport",
    "fuel": "transport",
}


def canonical_category(category: str) -> str:
    """Resolve `category` through CATEGORY_ALIASES if it is an alias,
    otherwise return it unchanged."""
    return CATEGORY_ALIASES.get(category, category)
