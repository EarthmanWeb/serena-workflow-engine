---
name: Input Normalization Policy
description: Standing policy for accepting user-friendly aliases on any category/label input while always persisting and exporting the canonical form. Authoritative — hidden acceptance tests assert on this exactly.
metadata:
  type: domain
---

# DOM_INPUT_NORMALIZATION — Category Alias Acceptance

This project has a fixed set of canonical category names. Users
frequently type a natural synonym instead of the canonical name. Every
current or future entry point that accepts a category as user input
(directly, or as a key inside a structured input such as a weights map)
must accept the documented alias table below **in addition to** the
canonical names, resolving an alias to its canonical form before any
further validation, storage, or output.

## Alias Table

| Alias  | Canonical   |
| ------ | ----------- |
| `food` | `groceries` |
| `car`  | `transport` |
| `fuel` | `transport` |

- This table applies wherever a category is accepted as input, with no
  exceptions for a particular entry point — the same alias must resolve
  the same way in every feature that takes a category.
- Once resolved, the canonical name is what gets stored, and what appears
  in every interactive display, generated report, and exported file — an
  alias never appears anywhere except as raw input.

Related: `mem:dom/DOM_MONEY_DISTRIBUTION` (aliases apply to distribution
recipient keys too), `mem:ref/REF_DATA_INTERCHANGE` (canonical names
always appear in exported output), `mem:arch/ARCH_LEDGERLITE`.
