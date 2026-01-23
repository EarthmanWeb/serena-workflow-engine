# _INDEX - Memory Navigation

<!-- TEMPLATE: Update during swe-init:
  - ## Active Features: Replace with actual FEATURE_* files
  - ## Current Session: Remove placeholder text
  Delete this comment after customization.
-->

## Quick Reference
- Features: [INDEX_FEATURES](INDEX_FEATURES)
- Architecture: [ARCH_INDEX](ARCH_INDEX)
- Workflows: [INDEX_WORKFLOWS_STATES](INDEX_WORKFLOWS_STATES)

## Memory Types

| Prefix | Purpose | Example |
|--------|---------|---------|
| FEATURE_ | Feature configurations | FEATURE_BACKEND |
| DOM_ | Domain behaviors | DOM_AUTH_LOGIN |
| SYS_ | System references | SYS_DATABASE |
| REF_ | Reference documentation | REF_DEV_STANDARDS |
| INDEX_ | Navigation indexes | INDEX_FEATURES |
| WF_ | Workflow state definitions | WF_START |
| WORKING_MEMORY_ | Session state | WORKING_MEMORY_20260115_task |
| SPEC_ | Specifications | SPEC_NEW_FEATURE |
| LITE_MODE_ | Lightweight session marker | LITE_MODE_abc12345 |

## Context Optimization

| Memory | Purpose |
|--------|---------|
| `WF_QUICKSTART` | Consolidated init (replaces reading 3 files) |
| `WF_RESEARCH_LITE` | Minimal path for simple lookups |

## Workflow Routing

| Situation | Go To |
|-----------|-------|
| Simple lookup ("find X") | `WF_RESEARCH_LITE` ⚡ |
| Starting work (full) | `WF_QUICKSTART` or `WF_START` |
| Researching | `WF_RESEARCH` |
| Making changes | `WF_CLASSIFY` |

## Active Features
- [FEATURE_X](FEATURE_X) - Description

## Current Session
- **Working Memory**: [WORKING_MEMORY_file]
- **State**: [WF_STATE]

## Getting Started
1. Read this index
2. Read [INDEX_FEATURES](INDEX_FEATURES)
3. Read relevant FEATURE_* for your task
4. Follow workflow states
