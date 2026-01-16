# REF_WORKING_MEMORY

## Naming

`WORKING_MEMORY_<YYYYMMDD>_<descriptor>.md`

Example: `WORKING_MEMORY_20260116_theme_refactor`

**Format:**
- Date: `YYYYMMDD` (e.g., 20260116)
- Descriptor: 2-4 words, snake_case (e.g., `theme_refactor`, `plugin_core_implementation`)

## Create

1. Get today's date: `YYYYMMDD` format
2. Pick descriptor (2-4 words, snake_case)
3. Write file
4. Echo to chat: `📋 Working Memory: WORKING_MEMORY_<YYYYMMDD>_<descriptor>`

## Load

1. Read file
2. **Verify descriptor matches chat context** - if not, wrong file
3. Echo to chat: `📋 Working Memory: WORKING_MEMORY_<timestamp>_<descriptor>`

## Update (BLOCKING REQUIREMENT)

**After ANY of these, you MUST update WORKING_MEMORY before next action:**
- Memory edit (write_memory, edit_memory)
- File edit (replace_symbol_body, insert_*)
- Workflow step transition
- Tool result that changes task state

**Steps:**
1. Write changes
2. Echo to chat: `📋 Working Memory: WORKING_MEMORY_<timestamp>_<descriptor>`

**PROCEEDING WITHOUT UPDATE = WORKFLOW VIOLATION**

**Echoing keeps the active ID in context window across long conversations.**

## Template

```markdown
# Working Memory

## Chat: <descriptor>
Created: <YYYYMMDD>

## Current Task
**[STATUS]**: [Task Name]

### Context
[1-2 sentences]

### Feature(s)
[Single feature key OR comma-separated list for multi-feature tasks]

### Affected Features (multi-feature only)
- **Primary**: [KEY1] - [why primary]
- **Secondary**: [KEY2] - [involvement reason]
- **Related**: [KEY3] - [involvement reason]

### Progress
- [ ] Step 1
- [x] Step 2

**Files:** `path/to/file.php` - [note]

## Previous Task
**[OUTCOME]**: [Task name] - [summary]
```

**Note:** The `### Affected Features` section is only required when task spans multiple features. Omit for single-feature tasks.

## Workflow Context Section (Optional)

When a skill is invoked from a workflow, add this section:

```markdown
## Workflow Context
- **Calling Step**: WF_CLASSIFY
- **Feature Key(s)**: BLOCKS, CONTEXT_PROVIDERS
- **Session ID**: 20260109_145230
- **Return Step**: WF_DETECT_REQ
- **Invocation Mode**: workflow
```

**Fields:**
- `Calling Step`: Which WF_* invoked the skill
- `Feature Key(s)`: Active feature(s) from INDEX_FEATURES (comma-separated if multiple)
- `Session ID`: Timestamp from WORKING_MEMORY filename
- `Return Step`: Where to return after skill completion
- `Invocation Mode`: `workflow` | `standalone` | `swarm_agent`

---

## Skill Return Section (Optional)

When a skill completes, add this section:

```markdown
## Skill Return
- **Skill**: research
- **Status**: success_with_findings
- **Findings Summary**: [brief summary]
- **Artifacts**: [list of outputs]
- **Next Step Hint**: WF_DETECT_REQ
- **Context Updates**: [any state changes]
```

**Status codes:**
- `success` - Completed normally → go to return_step
- `success_with_findings` - Completed with artifacts → go to return_step
- `needs_clarification` - Cannot proceed → go to WF_CLARIFY
- `blocked` - Hit blocker → go to WF_CLARIFY
- `escalate_complexity` - More complex → go to WF_SWARM_ORCHESTRATE

See `REF_SKILL_PROTOCOLS` for full specification.

---

## Rules

1. One file per conversation (timestamp ensures uniqueness)
2. Echo ID on every operation (keeps ID in context)
3. Verify descriptor on load (confirms correct file)
4. One Current Task, one Previous Task
5. Update after significant actions
6. Add Workflow Context when skill invoked from workflow
7. Add Skill Return when skill completes in workflow mode
