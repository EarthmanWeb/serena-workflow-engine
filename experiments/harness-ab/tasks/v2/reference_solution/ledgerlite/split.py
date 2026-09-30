"""Split transaction allocation (largest-remainder method)."""

from .errors import E_SPLIT_WEIGHTS, LedgerError


def allocate(total_cents: int, weights: dict) -> dict:
    """Allocate `total_cents` across the categories in `weights` (category ->
    positive integer weight) using the largest-remainder method.

    Each category's raw share is `total_cents * weight / sum(weights)`. Each
    category first receives `floor(raw_share)` cents. The leftover cents
    (`total_cents - sum(floor shares)`) are distributed one cent at a time to
    the categories with the largest fractional remainder, ties broken by
    picking the alphabetically-first category name first.

    Raises LedgerError(E_SPLIT_WEIGHTS) if weights is empty, or if any weight
    is not a positive integer (zero, negative, or non-integer).
    """
    if not weights:
        raise LedgerError(E_SPLIT_WEIGHTS, "no shares given")

    for category, weight in weights.items():
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            raise LedgerError(
                E_SPLIT_WEIGHTS, f"share weight for {category!r} must be a positive integer"
            )

    total_weight = sum(weights.values())
    negative = total_cents < 0
    abs_total = abs(total_cents)

    shares = {}
    remainders = {}
    allocated = 0
    for category, weight in weights.items():
        raw = abs_total * weight
        whole, rem = divmod(raw, total_weight)
        shares[category] = whole
        remainders[category] = rem
        allocated += whole

    leftover = abs_total - allocated

    order = sorted(weights.keys(), key=lambda c: (-remainders[c], c))
    for category in order[:leftover]:
        shares[category] += 1

    if negative:
        return {category: -cents for category, cents in shares.items()}
    return dict(shares)
