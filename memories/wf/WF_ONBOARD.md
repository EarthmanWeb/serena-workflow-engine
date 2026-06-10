# WF_ONBOARD - Feature Onboarding

> **On step WF_ONBOARD**

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
/swe-feature-onboard
```

Or with options:

```
/swe-feature-onboard [KEY]        # Pre-fill feature key
/swe-feature-onboard [KEY] --quick # Quick mode (minimal)
```

## Routing

| Condition                           | Read Next              |
| ----------------------------------- | ---------------------- |
| Feature configured (DAA swarm used) | `WF_SWARM_ORCHESTRATE` |
| Feature configured (quick/manual)   | `WF_START`             |
| Feature configured (task pending)   | `WF_CLASSIFY`          |
| User cancelled                      | End conversation       |
