# REF_SWE_DEVELOPMENT - Plugin Development Standards

## Purpose
Standards for developing and maintaining the Serena Workflow Engine plugin.

## Dual-Location Architecture

SWE operates with files in TWO locations:

| Location | Path | Purpose |
|----------|------|---------|
| **Plugin Folder** | `.claude/plugins/serena-workflow-engine/` | Generic/portable code |
| **Local Memories** | `.serena/memories/` | Project-specific adaptations |

## Change Classification

### Generic Changes → Update BOTH Locations

| Change Type | Plugin File | Local Memory | Action |
|-------------|-------------|--------------|--------|
| New workflow state | `state-machine/instructions/WF_*.md` | `WF_*.md` | Create in plugin, copy to memories |
| Reference doc | `state-machine/references/REF_*.md` | `REF_*.md` | Create in plugin, copy to memories |
| Hook behavior | `hooks/*.py` | N/A | Edit plugin only |
| New skill/command | `skills/` or `commands/` | N/A | Plugin only |

### Project-Specific Changes → Local Only

| Change Type | Where |
|-------------|-------|
| Custom DOM_* docs | `.serena/memories/` only |
| Custom SYS_* docs | `.serena/memories/` only |
| Project REF_* docs | `.serena/memories/` only |
| FEATURE_* configs | `.serena/memories/` only |

## Hook Sync Requirements (CRITICAL)

When modifying hooks, THREE files must stay synchronized:

1. **Hook Script:** `.claude/plugins/serena-workflow-engine/hooks/*.py`
2. **hooks.json:** `.claude/plugins/serena-workflow-engine/hooks/hooks.json`
   - Uses `${CLAUDE_PLUGIN_ROOT}` paths
3. **settings.json:** `.claude/settings.json`
   - Uses literal paths: `.claude/plugins/serena-workflow-engine/hooks/*.py`

### Path Translation Table

| hooks.json | settings.json |
|------------|---------------|
| `${CLAUDE_PLUGIN_ROOT}/hooks/file.py` | `.claude/plugins/serena-workflow-engine/hooks/file.py` |

### Verification

```bash
# Verify hooks match (ignoring path syntax)
diff <(jq -S '.hooks' .claude/plugins/serena-workflow-engine/hooks/hooks.json) \
     <(jq -S '.hooks' .claude/settings.json | \
       sed 's|\.claude/plugins/serena-workflow-engine|\${CLAUDE_PLUGIN_ROOT}|g')
```

## Adding New Workflow State

1. Create instruction: `state-machine/instructions/WF_NEWSTATE.md`
2. Update `states.json` with state definition
3. Copy to local memories: `cp ... .serena/memories/WF_NEWSTATE.md`
4. Document in DOM_SWE_STATE_MACHINE

## Adding New Hook

1. Create script: `hooks/new_hook.py`
2. Update `hooks/hooks.json` (with `${CLAUDE_PLUGIN_ROOT}`)
3. Update `.claude/settings.json` (with literal path)
4. Document in DOM_SWE_HOOKS
5. Test: `python3 hooks/new_hook.py < /dev/null`

## Pre-Commit Checklist

- [ ] Generic changes synced to BOTH locations
- [ ] Project-specific changes in local memories ONLY
- [ ] Hook changes synced across all three files
- [ ] states.json updated if new states added
- [ ] Documentation updated (DOM_SWE_*, README)
- [ ] Tests pass: `jq . state-machine/states.json`

## Related Docs
- `DOM_SWE_DEVELOPMENT` - Project-specific development docs
- `DOM_SWE_HOOKS` - Hook architecture details
- `DOM_SWE_STATE_MACHINE` - State transition logic
