# _INDEX - Navigation Hub

## Workflow Feature Memories

| Memory                   | Purpose                     |
| ------------------------ | --------------------------- |
| `FEATURE_SWE`            | Workflow system scope       |
| `ARCH_SWE`               | Workflow architecture       |
| `INDEX_WORKFLOWS_STATES` | State inventory (19 states) |
| `CLAUDE_WORKFLOW`        | Visual state diagram        |
| `SPEC_WORKFLOW_SKILLS`   | Skill conversion spec       |
| `REF_SKILL_PROTOCOLS`    | WCP/SRP protocols           |
| `REF_WM`                 | Session state format        |

## Workflow Routing

| Situation                  | Go To                                         |
| -------------------------- | --------------------------------------------- |
| Simple lookup ("find X")   | `WF_RESEARCH`                                 |
| Starting work (full)       | `WF_INIT`                                     |
| Researching                | `WF_RESEARCH`                                 |
| Making changes             | `WF_CLASSIFY`                                 |
| Continuing                 | `WF_CONTINUE`                                 |
| Verifying                  | `WF_VERIFY`                                   |
| Modify workflow system     | `FEATURE_SWE`, `ARCH_SWE`                     |
| Understand workflow states | `INDEX_WORKFLOWS_STATES`, `CLAUDE_WORKFLOW`   |
| Add workflow-aware skill   | `SPEC_WORKFLOW_SKILLS`, `REF_SKILL_PROTOCOLS` |

## Context Optimization

| Memory             | Purpose                               |
| ------------------ | ------------------------------------- |
| `WF_RESEARCH_LITE` | User-requested only (not auto-routed) |
