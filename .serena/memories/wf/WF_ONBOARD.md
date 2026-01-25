# WF_ONBOARD - Feature Onboarding

> **On step WF_ONBOARD**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

This workflow runs when a feature needs to be registered in the workflow system.

## Triggers

- No feature indexed in INDEX_FEATURES
- User requests feature setup
- Active feature has no FEATURE_[KEY] memory

## Action

**Run the onboarding skill:**

```
/swe-onboard-feature
```

Or with options:
```
/swe-onboard-feature [KEY]        # Pre-fill feature key
/swe-onboard-feature [KEY] --quick # Quick mode (minimal)
```

## MANDATORY NEXT STEP

| Condition | MUST Read Next |
|-----------|----------------|
| Feature configured | `WF_START` |
| User cancelled | End conversation |

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**
