# REF_WORKING_MEMORY

## Naming

`WORKING_MEMORY_<SESSION_ID>_<descriptor>.md`

Example: `WORKING_MEMORY_3fe6b3c5_theme_refactor`

**Format:**
- Session ID: 8-character unique conversation identifier (from `transcript_path` UUID)
- Descriptor: 2-4 words, snake_case (e.g., `theme_refactor`, `plugin_core_implementation`)

**Session ID Source:**
The session ID is extracted from Claude Code's `transcript_path` which contains a UUID per conversation:
```
~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl
                       ^^^^^^^^ (first 8 chars = session ID)
```

This ensures each conversation has a truly unique working memory file.

## Create

1. Get session ID from hook context (e.g., `Session: 3fe6b3c5`)
2. Pick descriptor (2-4 words, snake_case)
3. Write file
4. Echo to chat: `📋 Working Memory: WORKING_MEMORY_<SESSION_ID>_<descriptor>`

## Load

1. Read file
2. **Verify session ID matches current session** - if not, wrong file
3. Echo to chat: `📋 Working Memory: WORKING_MEMORY_<SESSION_ID>_<descriptor>`

## Update (BLOCKING REQUIREMENT)

**After ANY of these, you MUST update WORKING_MEMORY before next action:**
- Memory edit (write_memory, edit_memory)
- File edit (replace_symbol_body, insert_*)
- Workflow step transition
- Tool result that changes task state

**Steps:**
1. Write changes
2. Echo to chat: `📋 Working Memory: WORKING_MEMORY_<SESSION_ID>_<descriptor>`

**PROCEEDING WITHOUT UPDATE = WORKFLOW VIOLATION**

**Echoing keeps the active ID in context window across long conversations.**

## Template

```markdown
# Working Memory

## Chat: <descriptor>
Session: <SESSION_ID>

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

## Workflow Context Section (REQUIRED for Stop Hook)

**This section is REQUIRED for the workflow stop hook to function.**

The stop hook reads state from this section to warn about incomplete work.

```markdown
## Workflow Context
- **Calling Step**: WF_CLASSIFY
- **Feature Key(s)**: BLOCKS, CONTEXT_PROVIDERS
- **Session ID**: 20260109_145230
- **Return Step**: WF_DETECT_REQ
- **Invocation Mode**: workflow
- **Current State**: WF_EXECUTE
```

**Fields:**
- `Calling Step`: Which WF_* invoked the current skill/action
- `Current State`: **CRITICAL** - Active workflow state (used by stop hook)
- `Feature Key(s)`: Active feature(s) from INDEX_FEATURES (comma-separated if multiple)
- `Session ID`: 8-char unique ID from transcript_path UUID (e.g., `3fe6b3c5`)
- `Return Step`: Where to return after skill completion
- `Invocation Mode`: `workflow` | `standalone` | `swarm_agent`

**Stop Hook Behavior:**
The stop hook checks `Current State` (or falls back to `Calling Step`) to detect incomplete work:

| State | Stop Behavior |
|-------|---------------|
| `WF_DONE`, `WF_CLEANUP` | Clean exit - no warning |
| `WF_EXECUTE`, `WF_DEBUG_TDD`, `WF_VERIFY`, `WF_PLAN_ARCHITECTURE` | ⚠️ Warning: "Stopping with incomplete work" |
| `UNINITIALIZED` | Clean exit - no warning |

**IMPORTANT:** Always update `Current State` when transitioning between workflow steps to ensure accurate stop hook behavior.

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
