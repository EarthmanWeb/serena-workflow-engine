# CLAUDE.md - SPS Development Reference

Project-specific AI guidance for SPS development patterns and architecture.

## Mandatory Hook Actions

Hooks will send you data to guide you. ALWAYS LISTEN TO THEM.
- Did you follow hook instructions exactly?
- Did you read all references mentioned in hook responses COMPLETELY?
- Did you check INDEX_FEATURES or _INDEX for existing features?
- Did you use Serena tools before Read/Edit?
- Did you log findings to WM?
- Did you update WM after significant steps?

## 🎯 Core Principles

**KISS → DRY → YAGNI** (priority order)
- Simple, readable code
- Extract at 3+ occurrences
- Build only when needed

**"Let It Fail":** Avoid / Remove defensive code | Clear failures | No fallback masking

## Important Reminders

Do what's asked - nothing more, nothing less. NEVER create files unnecessarily. ALWAYS edit existing files. NEVER proactively create documentation unless explicitly requested.