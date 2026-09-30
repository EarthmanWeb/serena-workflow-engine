---
name: WF_VERIFY Gherkin Spec Coverage Check
description: How to verify Gherkin spec coverage at WF_VERIFY — when existing specs exist for the affected feature, or WM carries gherkin_spec_update true.
metadata:
  type: reference
obligations:
  - When the affected feature has existing .feature specs, every behavioral change this task made MUST be reflected in both specs and tests before WF_DONE.
---

# WF_VERIFY — Gherkin Spec Coverage Check

Run when the affected feature has existing Gherkin specs OR WM contains `gherkin_spec_update: true`.

## Check for Existing Specs

- `Glob(pattern="tests/specs/*[feature-key]*.feature")`
- `mcp__plugin_swe_serena__list_memories(topic="spec")`

## If Specs Exist — Verify Coverage

For each existing `.feature` file related to the affected feature:

1. Read the spec; extract all Given/When/Then/And steps.
2. Compare against changes made — did this task add or modify behavior covered by the spec?
3. Check for gaps:
   - New behavior added NOT covered by existing spec scenarios → spec update needed.
   - Existing spec scenarios that now behave differently due to changes → spec update needed.
   - All changed behavior covered by existing specs → pass.

## If Spec Updates Needed

Invoke `/swe-gherkin-spec` to add scenarios covering the new behavior, then `/swe-gherkin-dev` to create matching tests.

This is NOT optional when specs exist. When a feature has Gherkin specs, every behavioral change MUST be reflected in both the specs and their tests.

## If No Specs Exist

Skip this section. Gherkin specs are enforced at WF_ARCH_REVIEW for new features. Do NOT retroactively require specs on existing features without specs unless the user requests it.
