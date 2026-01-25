#!/bin/bash
# Auto-bump plugin version
# Run this before commit or use as pre-commit hook

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
PLUGIN_JSON="$PLUGIN_ROOT/.claude-plugin/plugin.json"
MARKETPLACE_JSON="$PLUGIN_ROOT/.claude-plugin/marketplace.json"

# Check if jq is available
if ! command -v jq &> /dev/null; then
    echo "Error: jq required but not installed"
    echo "Install with: brew install jq"
    exit 1
fi

# Check if files exist
if [[ ! -f "$PLUGIN_JSON" ]]; then
    echo "Error: plugin.json not found at $PLUGIN_JSON"
    exit 1
fi

if [[ ! -f "$MARKETPLACE_JSON" ]]; then
    echo "Error: marketplace.json not found at $MARKETPLACE_JSON"
    exit 1
fi

# Get current version
CURRENT_VERSION=$(jq -r '.version' "$PLUGIN_JSON")

# Parse version components
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"

# Increment patch version
NEW_PATCH=$((PATCH + 1))
NEW_VERSION="$MAJOR.$MINOR.$NEW_PATCH"

echo "Bumping version: $CURRENT_VERSION -> $NEW_VERSION"

# Update plugin.json
jq --arg v "$NEW_VERSION" '.version = $v' "$PLUGIN_JSON" > "$PLUGIN_JSON.tmp" && mv "$PLUGIN_JSON.tmp" "$PLUGIN_JSON"

# Update marketplace.json (both root version and plugin version)
jq --arg v "$NEW_VERSION" '.version = $v | .plugins[0].version = $v' "$MARKETPLACE_JSON" > "$MARKETPLACE_JSON.tmp" && mv "$MARKETPLACE_JSON.tmp" "$MARKETPLACE_JSON"

echo "✅ Version bumped to $NEW_VERSION"
echo ""
echo "Files updated:"
echo "  - $PLUGIN_JSON"
echo "  - $MARKETPLACE_JSON"
