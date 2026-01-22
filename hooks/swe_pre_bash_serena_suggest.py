#!/usr/bin/env python3
"""PreToolUse hook for Bash - Detect search commands and suggest Serena tools instead.

Fuzzy matches search terms against FEATURE_* memories and _INDEX entries.
Blocks with strong directive to use Serena's indexed tools for better results.
"""

import os
import sys
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_block
    from swe_hooks.core.input import read_stdin_safe, get_input_field
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

# Search command patterns - extract the search term
SEARCH_PATTERNS = [
    # grep variants
    (r'grep\s+(?:-[a-zA-Z]+\s+)*["\']?([^"\'|\s]+)', 'grep'),
    (r'grep\s+(?:-[a-zA-Z]+\s+)*"([^"]+)"', 'grep'),
    (r"grep\s+(?:-[a-zA-Z]+\s+)*'([^']+)'", 'grep'),
    # ripgrep
    (r'rg\s+(?:-[a-zA-Z]+\s+)*["\']?([^"\'|\s]+)', 'rg'),
    (r'rg\s+(?:-[a-zA-Z]+\s+)*"([^"]+)"', 'rg'),
    (r"rg\s+(?:-[a-zA-Z]+\s+)*'([^']+)'", 'rg'),
    # find
    (r'find\s+\S+\s+-name\s+["\']?\*?([^"\'*\s]+)', 'find'),
    (r'find\s+\S+\s+-iname\s+["\']?\*?([^"\'*\s]+)', 'find'),
    # ag (silver searcher)
    (r'ag\s+(?:-[a-zA-Z]+\s+)*["\']?([^"\'|\s]+)', 'ag'),
    (r'ag\s+(?:-[a-zA-Z]+\s+)*"([^"]+)"', 'ag'),
    # ack
    (r'ack\s+(?:-[a-zA-Z]+\s+)*["\']?([^"\'|\s]+)', 'ack'),
    (r'ack\s+(?:-[a-zA-Z]+\s+)*"([^"]+)"', 'ack'),
    # fd (find alternative)
    (r'fd\s+(?:-[a-zA-Z]+\s+)*["\']?([^"\'|\s]+)', 'fd'),
    # cat with grep
    (r'cat\s+\S+\s*\|\s*grep\s+["\']?([^"\'|\s]+)', 'cat|grep'),
]

# Known feature keywords for fuzzy matching
FEATURE_KEYWORDS = {
    'BLOCKS': ['block', 'blocks', 'acf', 'editor', 'gutenberg', 'sps-block', 'render', 'fields'],
    'CONTEXT_PROVIDERS': ['provider', 'context', 'blade', 'bladeone', 'view', 'viewmodel', 'template-data'],
    'THEME_BASE': ['theme', 'base-theme', 'sps-base', 'parent-theme', 'base-blade'],
    'THEME_DISTRICT': ['district', 'sps-district', 'district-blade'],
    'THEME_SCHOOLS': ['schools', 'sps-schools', 'schools-blade'],
    'THEME_MYSPS': ['mysps', 'my-sps', 'mysps-blade'],
    'TESTS': ['test', 'tests', 'playwright', 'spec', 'fixture', 'e2e'],
    'WORKFLOWS': ['workflow', 'swe', 'hook', 'hooks', 'state-machine', 'wf_'],
    'LEGACY': ['legacy', 'old', 'migration', 'mu-plugins-legacy', 'themes-legacy'],
}

# Index keywords from _INDEX
INDEX_KEYWORDS = {
    '_INDEX': ['index', 'navigation', 'hub', 'lookup'],
    'SYS_BLOCKS': ['notification', 'block-system', 'registration'],
    'ARCH_BLOCKS': ['architecture', 'block-arch'],
    'SYS_CONTEXT_PROVIDERS': ['provider-inventory', 'provider-list'],
    'ARCH_PROVIDERS': ['provider-architecture'],
    'ARCH_THEMES': ['theme-architecture'],
    'ARCH_TESTS': ['test-architecture'],
    'INDEX_BLOCKS_TEMPLATES': ['block-template', 'blade-template'],
    'INDEX_BLOCKS_CLASSES': ['block-class'],
    'INDEX_BLOCKS_FUNCTIONS': ['block-function'],
    'INDEX_CONTEXT_PROVIDERS_CLASSES': ['provider-class'],
    'INDEX_CONTEXT_PROVIDERS_FUNCTIONS': ['provider-function'],
    'INDEX_TESTS_FIXTURES': ['fixture', 'test-fixture'],
    'INDEX_TESTS_HELPERS': ['helper', 'test-helper'],
    'REF_TESTS_AUTH': ['auth', 'authentication', 'login', 'loginAs'],
    'REF_TESTS_EDITOR_BLOCKS': ['editor-block', 'block-test'],
    'REF_BLADEONE': ['bladeone', 'blade', 'template-engine'],
    'MAP_LEGACY_FUNCTIONS': ['legacy-function', 'function-map'],
    'MAP_LEGACY_CLASSES': ['legacy-class', 'class-map'],
}


def fuzzy_match(term: str, keyword: str, threshold: float = 0.6) -> float:
    """Calculate fuzzy match score between term and keyword."""
    term_lower = term.lower()
    keyword_lower = keyword.lower()
    
    # Exact match
    if term_lower == keyword_lower:
        return 1.0
    
    # Substring match
    if term_lower in keyword_lower or keyword_lower in term_lower:
        return 0.9
    
    # Sequence matcher
    return SequenceMatcher(None, term_lower, keyword_lower).ratio()


def find_matching_memories(search_term: str, threshold: float = 0.5) -> list:
    """Find Serena memories that fuzzy match the search term."""
    matches = []
    
    # Check FEATURE memories
    for feature_key, keywords in FEATURE_KEYWORDS.items():
        for keyword in keywords:
            score = fuzzy_match(search_term, keyword)
            if score >= threshold:
                matches.append({
                    'memory': f'FEATURE_{feature_key}',
                    'keyword': keyword,
                    'score': score,
                    'type': 'feature'
                })
                break  # One match per feature is enough
    
    # Check INDEX memories
    for index_key, keywords in INDEX_KEYWORDS.items():
        for keyword in keywords:
            score = fuzzy_match(search_term, keyword)
            if score >= threshold:
                matches.append({
                    'memory': index_key,
                    'keyword': keyword,
                    'score': score,
                    'type': 'index'
                })
                break
    
    # Sort by score descending
    matches.sort(key=lambda x: x['score'], reverse=True)
    return matches[:5]  # Return top 5 matches


def extract_search_term(command: str) -> tuple:
    """Extract search term from command. Returns (term, tool_type) or (None, None)."""
    for pattern, tool_type in SEARCH_PATTERNS:
        match = re.search(pattern, command, re.IGNORECASE)
        if match:
            term = match.group(1)
            # Filter out common flags/options that might be captured
            if term.startswith('-') or len(term) < 2:
                continue
            return term, tool_type
    return None, None


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        command = get_input_field(input_data, 'tool_input', 'command', default='')

        if not command:
            output_empty()

        # Extract search term from command
        search_term, tool_type = extract_search_term(command)
        
        if not search_term:
            output_empty()
        
        # Find matching memories
        matches = find_matching_memories(search_term)
        
        if not matches:
            output_empty()
        
        # Build the directive message
        top_match = matches[0]
        memory_list = '\n'.join([f"  - {m['memory']} (matched: '{m['keyword']}', score: {m['score']:.2f})" for m in matches])
        
        directive = f"""
🛑 **SERENA INDEXED SEARCH AVAILABLE** - USE SERENA INSTEAD OF BASH

You are attempting to use `{tool_type}` to search for: **{search_term}**

Serena has **pre-indexed memories** that likely contain what you're looking for:

{memory_list}

## STRONG DIRECTIVE: USE SERENA TOOLS

Instead of running bash search commands, you MUST use Serena's semantic tools:

1. **For navigation/discovery:**
   ```
   mcp__serena__read_memory("_INDEX")
   ```

2. **For feature-specific context:**
   ```
   mcp__serena__read_memory("{top_match['memory']}")
   ```

3. **For finding symbols/code:**
   ```
   mcp__serena__find_symbol("{search_term}")
   ```

4. **For pattern search in code:**
   ```
   mcp__serena__search_for_pattern("{search_term}")
   ```

## WHY SERENA IS BETTER:

- Pre-indexed with semantic understanding of the codebase
- Feature memories contain curated, organized information
- Symbol lookups are faster and more accurate
- Maintains workflow context and learning

**DO NOT USE GREP/FIND/RG FOR CODEBASE SEARCHES. USE SERENA.**
"""
        
        output_block(directive)

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Pre-bash serena suggest error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
