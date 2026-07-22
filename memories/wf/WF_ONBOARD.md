---
name: WF_ONBOARD
description: Feature onboarding workflow — register a feature in the workflow system, then route by configuration method.
metadata:
  type: workflow
---

# WF_ONBOARD — Feature Onboarding

> **On step WF_ONBOARD**

## Triggers

- No feature indexed in `INDEX_FEATURES`.
- User requests feature setup.
- Active feature has no `FEATURE_[KEY]` memory.

## Action

Run the onboarding skill:

- `/swe-feature-onboard` — default.
- `/swe-feature-onboard [KEY]` — pre-fill feature key.
- `/swe-feature-onboard [KEY] --quick` — quick mode (minimal).

## Routing

| Condition                           | Read Next              |
| ----------------------------------- | ---------------------- |
| Feature configured (DAA swarm used) | `WF_SWARM_ORCHESTRATE` |
| Feature configured (quick/manual)   | `WF_CLASSIFY`          |
| Feature configured (task pending)   | `WF_CLASSIFY`          |
| User cancelled                      | End conversation       |
