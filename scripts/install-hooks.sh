#!/bin/bash
# Install git hooks for SWE plugin
# Run this once after cloning

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"

# Find the actual git hooks directory (handles submodules)
cd "$PLUGIN_ROOT"
GIT_DIR=$(git rev-parse --git-dir)
HOOKS_DIR="$GIT_DIR/hooks"

echo "Installing hooks to: $HOOKS_DIR"

# Create hooks directory if it doesn't exist
mkdir -p "$HOOKS_DIR"

# Symlink pre-commit hook
ln -sf "$SCRIPT_DIR/pre-commit" "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-commit"
chmod +x "$SCRIPT_DIR/pre-commit"
chmod +x "$SCRIPT_DIR/bump-version.sh"

echo "✅ Git hooks installed successfully"
echo ""
echo "The pre-commit hook will automatically bump the version on each commit."
