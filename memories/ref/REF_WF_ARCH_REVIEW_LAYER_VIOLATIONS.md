---
name: WF_ARCH_REVIEW Layer Violation Catalogue
description: STOP-condition catalogue for the Architecture Compliance Check — generic layer violations, presentation-layer rules, project-specific checks.
metadata:
  type: reference
obligations:
  - Revise the design when the current design matches any item below; read REF_* memories for the correct pattern before re-proposing.
---

# WF_ARCH_REVIEW — STOP Conditions (Layer Violation Catalogue)

Revise the design when any apply. Read `REF_*` memories for correct patterns.

## General Layer Violations

- Business logic in presentation layer (views/templates only display data).
- Presentation layer calling data layer directly (must go through business logic).
- Data-access layer containing business rules (must be in service/business layer).
- Cross-cutting concerns scattered instead of centralized.

## Presentation Layer

- View contains complex logic beyond simple conditionals.
- View has data transformations that belong in business layer.
- View imports services/functions directly instead of using provided context.

## Project-Specific Violations

- Any compliance-checklist item (Step 2c) the design would violate.
- New files that do not follow naming conventions from `DEV_*` memories.
- Missing integration points (registration, enqueuing, discovery).
