---
name: Split Allocation
description: Exact algorithm for allocating a split transaction's total across category shares, and the resulting child-transaction naming. Authoritative — hidden acceptance tests grade against this algorithm exactly.
metadata:
  type: domain
---

# DOM_SPLIT_ALLOCATION — Split Transaction Allocation Rules

A split transaction divides one `total_cents` amount across several
categories using integer weights (`shares: dict[str, int]`). The allocation
is NOT simple rounding per-category — it must use the **largest-remainder
method** so every cent is accounted for and results are deterministic.

## Algorithm

1. `total_weight = sum(weights.values())`.
2. For each category, compute the raw share
   `abs(total_cents) * weight / total_weight` and take the integer floor as
   that category's base allocation. Track the fractional remainder of each
   division.
3. `leftover = abs(total_cents) - sum(base allocations)` (the cents not yet
   assigned due to flooring).
4. Distribute `leftover` **one cent at a time** to the categories with the
   **largest fractional remainder**, largest first.
5. **Tie-break**: when two or more categories have equal remainders,
   assign the leftover cent to whichever is **alphabetically first by
   category name** — never by dict/insertion order, never by original
   weight.
6. If `total_cents` is negative, negate every category's final allocation
   (the sign is applied after allocation, not before).

## Validation

- `shares` must be non-empty.
- Every weight must be a positive integer (`> 0`). Zero, negative, or
  non-integer weights raise `LedgerError(E_SPLIT_WEIGHTS, ...)` — see
  `mem:ref/REF_ERROR_CODES`.

## Child Transaction Naming

- `Store.add_split` creates one child `Transaction` per category.
- Each child's `description` is `"<original description> [split i/n]"`
  where `n` is the number of categories in the split and `i` is that
  child's **1-based position when categories are sorted alphabetically**
  (not the order shares were passed in, not weight order).
- Example: `add_split(..., "Trip", -1000, {"transport": 1, "groceries": 1})`
  produces `groceries` as `"Trip [split 1/2]"` and `transport` as
  `"Trip [split 2/2]"` (groceries sorts before transport).

Related: `mem:feature/FEATURE_LEDGER`, `mem:ref/REF_ERROR_CODES`
(E_SPLIT_WEIGHTS), `mem:dom/DOM_LEDGER_RULES` (category aliases apply to
split shares too).
