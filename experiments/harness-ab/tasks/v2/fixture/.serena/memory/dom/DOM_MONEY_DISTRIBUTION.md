---
name: Money Distribution Policy
description: Standing policy for dividing one monetary amount across multiple recipients/buckets by weight, including tie-breaking and the naming of the resulting derived records. Authoritative — read before implementing any feature that divides an amount by weight.
metadata:
  type: domain
---

# DOM_MONEY_DISTRIBUTION — Weighted Amount Distribution Policy

Whenever a feature divides one integer-cents amount among several
recipients or buckets according to integer weights, it must use the
**largest-remainder method** described below, not naive per-bucket
rounding. Naive rounding (e.g. rounding each share independently) loses or
invents cents and produces non-deterministic totals; the largest-remainder
method guarantees every cent is accounted for and the result is
reproducible for the same inputs.

## Algorithm

1. Let `total_weight` be the sum of all weights.
2. For each recipient, compute the raw share as
   `abs(total) * weight / total_weight` and take the integer floor as that
   recipient's base allocation. Track the fractional remainder dropped by
   the floor.
3. Let `leftover` be `abs(total) - sum(base allocations)` — the cents not
   yet assigned because of flooring.
4. Distribute `leftover` one cent at a time to the recipients with the
   **largest fractional remainder**, largest first.
5. **Tie-break rule**: when two or more recipients have an equal
   remainder, the leftover cent goes to whichever recipient's key sorts
   **alphabetically first** — never dict/insertion order, never original
   weight order. Continue down the alphabetical tie order for each
   additional leftover cent that ties.
6. If `total` is negative, negate every recipient's final allocation after
   the allocation above is computed on the absolute value (the sign is
   applied last, not distributed per-recipient before allocation).

## Validation

- The weights map must be non-empty.
- Every weight must be a positive integer (`> 0`). Zero, negative, or
  non-integer weights are invalid input — reject the whole distribution
  rather than silently dropping or zeroing a share (see
  `mem:ref/REF_ERROR_HANDLING` for how to signal this).

## Worked Example (invoice split, illustrative only — not this project's domain)

Splitting an invoice total of 100 cents three ways with equal weights
`{"acme": 1, "bolt": 1, "cogs": 1}` gives a raw share of 33.33 cents each —
33, 33, 33 floored, with 1 leftover cent. All three remainders tie at
`0.33`, so the leftover cent goes to `"acme"` (alphabetically first),
giving `acme=34, bolt=33, cogs=33`.

Splitting 11 cents with weights `{"acme": 3, "bolt": 2}` gives raw shares
`6.6` and `4.4` — floored to `6` and `4`, with 1 leftover cent. `"acme"`'s
remainder (`0.6`) is larger than `"bolt"`'s (`0.4`), so the tie-break rule
does not apply and the leftover cent goes to `"acme"`: `acme=7, bolt=4`.

## Derived Record Naming

- When a distribution produces one derived record per recipient (rather
  than only a numeric allocation), each derived record's label is the
  original record's label with the suffix `" [<i>/<n>]"` appended, where
  `n` is the number of recipients in the distribution and `i` is that
  recipient's **1-based position when recipient keys are sorted
  alphabetically** — not the order weights were supplied in, not weight
  order.
- Example: distributing an original label `"Trip"` across recipients
  `{"transport": 1, "groceries": 1}` (alphabetically: `groceries`,
  `transport`) produces derived labels `"Trip [1/2]"` for `groceries` and
  `"Trip [2/2]"` for `transport`.
- Any feature that returns the created derived records returns them in
  that same alphabetical-recipient order.

Related: `mem:arch/ARCH_LEDGERLITE`, `mem:ref/REF_ERROR_HANDLING` (invalid
weights), `mem:dom/DOM_INPUT_NORMALIZATION` (recipient/category keys may be
aliases on input; distribution operates on canonical keys).
