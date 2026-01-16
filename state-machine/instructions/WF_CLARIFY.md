# WF_CLARIFY

> **❓ On step WF_CLARIFY**

OUTPUT THE ABOVE LINE IMMEDIATELY.

---

## Purpose

Request clarification from user when information is ambiguous or missing.

## Entry

- **From**: Any state (*)
- **Triggers**: ambiguity_detected, missing_information

## Required Actions

1. `formulate_question` - Create clear, specific question
2. `present_options` - Offer choices when applicable
3. `await_response` - Wait for user input

## Permissions

- **Edit**: false | **Write**: false
- **Plan Mode**: never

## Question Guidelines

- Be specific about what's unclear
- Provide context for the question
- Offer options when possible
- Don't ask multiple questions at once

## Transitions

| Condition | Next State |
|-----------|------------|
| clarified | (return_to_caller) |

**Note**: Returns to the state that invoked WF_CLARIFY.

## RLVR Signal

- **Type**: clarify_visit | **Impact**: penalty (-0.1)

Frequent clarification visits indicate unclear requirements or poor analysis.

## MANDATORY NEXT STEP

Return to the calling state after clarification received.

**SKIPPING THIS TRANSITION = WORKFLOW VIOLATION**

[CRITICAL: Are you on a WF_* workflow step? Did you report on it?]
