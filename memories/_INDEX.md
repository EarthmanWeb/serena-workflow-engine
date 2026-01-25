# _INDEX - Navigation Hub

## Quick Access by Task

| Task | Memory to Read |
|------|----------------|
| Understand blocks architecture | `SYS_BLOCKS`, `ARCH_BLOCKS` |
| Add new block | `SYS_BLOCKS` → Block Registration |
| Edit block template | `SYS_BLOCKS` → Templates section |
| Work on notifications | `SYS_BLOCKS` → Notification System |
| Write block tests | `REF_TESTS_EDITOR_BLOCKS` |
| Write alert tests | `REF_TESTS_ALERTS` |
| Context provider work | `FEATURE_CONTEXT_PROVIDERS`, `SYS_CONTEXT_PROVIDERS` |
| Context provider classes | `INDEX_CONTEXT_PROVIDERS_CLASSES` |
| Context provider functions | `INDEX_CONTEXT_PROVIDERS_FUNCTIONS` |
| Context provider architecture | `ARCH_PROVIDERS` |
| Context anti-patterns | `REF_CONTEXT_ANTIPATTERNS` |
| BladeOne templates | `REF_BLADEONE` |
| Theme work (base) | `FEATURE_THEME_BASE`, `INDEX_THEME_BASE_TEMPLATES` |
| Theme work (district) | `FEATURE_THEME_DISTRICT`, `INDEX_THEME_DISTRICT_TEMPLATES` |
| Theme work (schools) | `FEATURE_THEME_SCHOOLS`, `INDEX_THEME_SCHOOLS_TEMPLATES` |
| Theme work (app) | `FEATURE_THEME_REDACTED`, `INDEX_THEME_REDACTED_TEMPLATES` |
| Theme architecture | `ARCH_THEMES` |
| **Development standards** | `REF_DEV_STANDARDS` |

## Development Standards

**Entry Point**: `REF_DEV_STANDARDS`

| Standard | Memory |
|----------|--------|
| PHP coding standards | `DEV_PHP` |
| JavaScript standards | `DEV_JAVASCRIPT` |
| SCSS/CSS standards | `DEV_SCSS` |
| BladeOne templates | `DEV_BLADEONE` |
| Playwright tests | `DEV_TESTS` |
| Build system | `DEV_BUILD` |
| Architecture patterns | `DEV_PATTERNS` |

## Feature Memories

| Memory | Purpose |
|--------|---------|
| `FEATURE_BLOCKS` | Feature scope and directories |
| `SYS_BLOCKS` | Complete block reference |
| `ARCH_BLOCKS` | Architecture documentation |
| `INDEX_BLOCKS_TEMPLATES` | Template inventory (46 templates) |
| `INDEX_BLOCKS_CLASSES` | Class inventory (3 classes) |
| `INDEX_BLOCKS_FUNCTIONS` | Function inventory (35 functions) |

## Context Provider Feature Memories

| Memory | Purpose |
|--------|---------|
| `FEATURE_CONTEXT_PROVIDERS` | Feature scope and directories |
| `SYS_CONTEXT_PROVIDERS` | Complete provider inventory |
| `ARCH_PROVIDERS` | Architecture documentation |
| `INDEX_CONTEXT_PROVIDERS_CLASSES` | Class inventory (23 providers + 3 traits) |
| `INDEX_CONTEXT_PROVIDERS_FUNCTIONS` | Function inventory (9 functions) |
| `REF_CONTEXT_ANTIPATTERNS` | Common mistakes to avoid |

## Theme Feature Memories

| Memory | Purpose |
|--------|---------|
| `FEATURE_THEME_BASE` | Base theme scope |
| `FEATURE_THEME_DISTRICT` | District child theme scope |
| `FEATURE_THEME_SCHOOLS` | Schools child theme scope |
| `FEATURE_THEME_REDACTED` | App child theme scope |
| `INDEX_THEME_*_TEMPLATES` | Template inventories |
| `ARCH_THEMES` | Theme architecture |

## Tests Feature Memories

| Memory | Purpose |
|--------|---------|
| `FEATURE_TESTS` | Test suite scope and skills |
| `ARCH_TESTS` | Test architecture and patterns |
| `INDEX_TESTS_FIXTURES` | Fixture inventory |
| `INDEX_TESTS_HELPERS` | Helper utility inventory |
| `INDEX_TESTS_CONFIG` | Configuration inventory |
| `REF_TESTS_AUTH` | Authentication patterns |
| `REF_TESTS_VISUAL` | Visual regression patterns |
| `REF_TESTS_EDITOR_BLOCKS` | Block testing patterns |
| `REF_TESTS_CACHE` | Cache invalidation patterns |
| `REF_TESTS_ALERTS` | Alert testing patterns |
| `REF_MCP_BROWSER` | Browser MCP reference (Playwright/DevTools) |
| `SYS_MCP_BROWSER_CONFIG` | Browser MCP project configuration |

## Key Files Quick Lookup

| Need to Find | File Path |
|--------------|-----------|
| Block registration | `mu-plugins/editor/init-blocks.php` |
| Notification system | `mu-plugins/editor/init-notifications.php` |
| Block fields | `mu-plugins/editor/fields/fields-*.php` |
| Block render | `mu-plugins/editor/custom-block/render.php` |
| Block JSON | `mu-plugins/editor/custom-block/block.json` |
| Templates | `mu-plugins/editor/templates/*.blade.php` |
| Notification templates | `mu-plugins/editor/templates/notifications/*.blade.php` |
| Context providers | `mu-plugins/blade-context-providers/providers/` |
| Base theme | `themes/base-blade/` |
| District theme | `themes/district-blade/` |
| Schools theme | `themes/schools-blade/` |
| App theme | `themes/app-blade/` |
| Theme templates | `themes/*/templates/*.blade.php` |

## Test Files Quick Lookup

| Test Type | Location |
|-----------|----------|
| Authentication | `private/tests/tests/00-user-authentication.spec.ts` |
| Terminus | `private/tests/tests/1-terminus.spec.ts` |
| Visual regression | `private/tests/tests/2-visual-regression-tests/` |
| Editor blocks | `private/tests/tests/3-editor-blocks/` |
| Content creation | `private/tests/tests/4-content-creation*.spec.ts` |
| iCal feeds | `private/tests/tests/5-ical-feeds.spec.ts` |
| Cache invalidation | `private/tests/tests/6-cache-invalidation/` |
| Functional tests | `private/tests/tests/7-functional-tests/` |
| Alerts/banners | `private/tests/tests/9-alerts/` |
| Fixtures | `private/tests/fixtures/` |
| Helpers | `private/tests/helpers/` |
| Config | `private/tests/config/` |

## Legacy Reference Memories

⚠️ **Legacy files are READ-ONLY reference snapshots - NEVER EDIT**

| Memory | Purpose |
|--------|---------|
| `FEATURE_LEGACY` | Legacy feature scope and usage rules |
| `MAP_LEGACY_QUICK` | Quick lookup for legacy → production mappings |
| `MAP_LEGACY_FUNCTIONS` | Complete function migration mapping (500+) |
| `MAP_LEGACY_CLASSES` | Complete class migration mapping (25+) |
| `MAP_LEGACY_DIRECTORIES` | Directory structure transformation |

## Legacy Files Quick Lookup

| Need to Compare | Legacy Path |
|-----------------|-------------|
| Legacy mu-plugins | `wp-content/mu-plugins-legacy/` |
| Legacy themes | `wp-content/themes-legacy/` |
| Legacy App theme | `wp-content/themes-legacy/app/` |
| Legacy District theme | `wp-content/themes-legacy/district/` |
| Legacy Schools theme | `wp-content/themes-legacy/schools/` |
| Legacy Base theme | `wp-content/themes-legacy/base-theme/` |
| Legacy backend functions | `wp-content/mu-plugins-legacy/backend-functions/` |
| Legacy theme functions | `wp-content/mu-plugins-legacy/theme-functions/` |
| Legacy configuration | `wp-content/mu-plugins-legacy/configuration/` |

## Workflow Feature Memories

| Memory | Purpose |
|--------|---------|
| `FEATURE_WORKFLOWS` | Workflow system scope |
| `ARCH_WORKFLOWS` | Workflow architecture |
| `INDEX_WORKFLOWS_STATES` | State inventory (19 states) |
| `CLAUDE_WORKFLOW` | Visual state diagram |
| `SPEC_WORKFLOW_SKILLS` | Skill conversion spec |
| `REF_SKILL_PROTOCOLS` | WCP/SRP protocols |
| `REF_WM` | Session state format |

## Context Optimization

| Memory | Purpose |
|--------|---------|
| `WF_RESEARCH_LITE` | User-requested only (not auto-routed) |

## Workflow Routing

| Situation | Go To |
|-----------|-------|
| Simple lookup ("find X") | `WF_RESEARCH` |
| Starting work (full) | `WF_INIT` |
| Researching | `WF_RESEARCH` |
| Making changes | `WF_CLASSIFY` |
| Continuing | `WF_CONTINUE` |
| Verifying | `WF_VERIFY` |
| Modify workflow system | `FEATURE_WORKFLOWS`, `ARCH_WORKFLOWS` |
| Understand workflow states | `INDEX_WORKFLOWS_STATES`, `CLAUDE_WORKFLOW` |
| Add workflow-aware skill | `SPEC_WORKFLOW_SKILLS`, `REF_SKILL_PROTOCOLS` |
