---
name: swe-symlink-memory
description: Set up auto-memory symlink to redirect Claude Code memory into project repo
---

# /swe-symlink-memory

Replace Claude Code's auto-memory directory with a symlink pointing to the project's `.serena/memory/` directory. This unifies auto-memory with Serena's memory system and makes memory files version-controllable.

## When to Run

- During `/swe-init` (Task 2 — runs FIRST, before bootstrap and onboarding, so memories written during init land in `.serena/memory/`)
- Standalone after cloning a repo that already uses SWE
- When setting up a new machine for an existing SWE project

## Process

### Step 1: Determine Paths

```bash
PROJECT_PATH=$(pwd)
SERENA_MEMORY_DIR="$PROJECT_PATH/.serena/memory"

# Claude Code encodes project paths by replacing both / and _ with -
ENCODED_PATH=$(echo "$PROJECT_PATH" | sed 's|[/_]|-|g')
AUTO_MEMORY_DIR="$HOME/.claude/projects/$ENCODED_PATH/memory"

# Verify: if the encoded dir doesn't exist, check for underscore-preserving variant
if [ ! -d "$HOME/.claude/projects/$ENCODED_PATH" ]; then
    ALT_ENCODED=$(echo "$PROJECT_PATH" | sed 's|/|-|g')
    if [ -d "$HOME/.claude/projects/$ALT_ENCODED" ]; then
        ENCODED_PATH="$ALT_ENCODED"
        AUTO_MEMORY_DIR="$HOME/.claude/projects/$ENCODED_PATH/memory"
        echo "Note: Using underscore-preserving encoding (older Claude Code version)"
    fi
fi

echo "Auto-memory path: $AUTO_MEMORY_DIR"
echo "Serena memory target: $SERENA_MEMORY_DIR"
```

### Step 2: Ensure Target Directory Exists

```bash
mkdir -p "$SERENA_MEMORY_DIR"
```

### Step 3: Migrate Existing Auto-Memory Content

Auto-memory files are flat (e.g., `feedback_test.md`, `user_role.md`). SWE organizes memories into typed subdirectories with uppercase names. This step migrates and reorganizes.

#### Prefix-to-Subdirectory Mapping

| Auto-Memory Pattern | Target Subdirectory | Rename Rule |
|---|---|---|
| `feedback_*.md` | `feedback/` | `FEEDBACK_*.md` |
| `user_*.md` | `user/` | `USER_*.md` |
| `project_*.md` | `project/` | `PROJECT_*.md` |
| `reference_*.md` | `ref/` | `REF_*.md` (note: `reference` → `ref`) |
| `SPEC_*.md` | `spec/` | Keep as-is (already uppercase) |
| `MEMORY.md` | root | **Merge** (see below) |
| Other `*.md` | root | Uppercase the filename |

#### Migration Script

```bash
if [ -d "$AUTO_MEMORY_DIR" ] && [ ! -L "$AUTO_MEMORY_DIR" ]; then
    FILE_COUNT=$(find "$AUTO_MEMORY_DIR" -maxdepth 1 -type f -name "*.md" | wc -l | tr -d ' ')
    if [ "$FILE_COUNT" -gt 0 ]; then
        echo "Found $FILE_COUNT file(s) in auto-memory directory — migrating with reorganization..."

        for f in "$AUTO_MEMORY_DIR"/*.md; do
            [ -f "$f" ] || continue
            basename=$(basename "$f")

            # Skip MEMORY.md — handled separately below
            [ "$basename" = "MEMORY.md" ] && continue

            # Determine target subdirectory and new filename
            case "$basename" in
                feedback_*)
                    subdir="feedback"
                    newname="$(echo "$basename" | sed 's/^feedback_/FEEDBACK_/' | tr '[:lower:]' '[:upper:]')"
                    # Preserve .md extension casing
                    newname="${newname%.MD}.md"
                    ;;
                user_*)
                    subdir="user"
                    newname="$(echo "$basename" | sed 's/^user_/USER_/' | tr '[:lower:]' '[:upper:]')"
                    newname="${newname%.MD}.md"
                    ;;
                project_*)
                    subdir="project"
                    newname="$(echo "$basename" | sed 's/^project_/PROJECT_/' | tr '[:lower:]' '[:upper:]')"
                    newname="${newname%.MD}.md"
                    ;;
                reference_*)
                    subdir="ref"
                    newname="$(echo "$basename" | sed 's/^reference_/REF_/' | tr '[:lower:]' '[:upper:]')"
                    newname="${newname%.MD}.md"
                    ;;
                SPEC_*)
                    subdir="spec"
                    newname="$basename"  # Already uppercase
                    ;;
                *)
                    subdir=""  # Root level
                    newname="$(echo "$basename" | tr '[:lower:]' '[:upper:]')"
                    newname="${newname%.MD}.md"
                    ;;
            esac

            # Create subdirectory if needed
            if [ -n "$subdir" ]; then
                mkdir -p "$SERENA_MEMORY_DIR/$subdir"
                target="$SERENA_MEMORY_DIR/$subdir/$newname"
            else
                target="$SERENA_MEMORY_DIR/$newname"
            fi

            if [ ! -f "$target" ]; then
                cp "$f" "$target"
                echo "  Migrated: $basename → ${subdir:+$subdir/}$newname"
            else
                echo "  Skipped (already exists): ${subdir:+$subdir/}$newname"
            fi
        done

        # Merge MEMORY.md
        SOURCE_MEMORY="$AUTO_MEMORY_DIR/MEMORY.md"
        TARGET_MEMORY="$SERENA_MEMORY_DIR/MEMORY.md"
        if [ -f "$SOURCE_MEMORY" ]; then
            echo "  Merging MEMORY.md index entries..."
            if [ ! -f "$TARGET_MEMORY" ]; then
                # No target — just copy (will be rewritten with updated paths)
                cp "$SOURCE_MEMORY" "$TARGET_MEMORY"
                echo "  Copied MEMORY.md (no existing target)"
            else
                # Append unique entries from source that aren't in target
                # Process each non-empty, non-heading line from source
                while IFS= read -r line; do
                    # Skip empty lines and heading lines
                    [ -z "$line" ] && continue
                    echo "$line" | grep -q '^#' && continue

                    # Extract the link target if it's a markdown link line
                    link_target=$(echo "$line" | sed -n 's/.*](\([^)]*\)).*/\1/p')
                    if [ -n "$link_target" ]; then
                        # Check if this link target (or its migrated version) already exists in target
                        if ! grep -qF "$link_target" "$TARGET_MEMORY"; then
                            echo "$line" >> "$TARGET_MEMORY"
                            echo "    Added entry: $line"
                        fi
                    fi
                done < "$SOURCE_MEMORY"
            fi

            # Rewrite paths in MEMORY.md to match new subdirectory structure
            sed -i '' \
                -e 's|(feedback_\([^)]*\))|(feedback/FEEDBACK_\U\1)|g' \
                -e 's|(user_\([^)]*\))|(user/USER_\U\1)|g' \
                -e 's|(project_\([^)]*\))|(project/PROJECT_\U\1)|g' \
                -e 's|(reference_\([^)]*\))|(ref/REF_\U\1)|g' \
                -e 's|(SPEC_\([^)]*\))|(spec/SPEC_\1)|g' \
                "$TARGET_MEMORY" 2>/dev/null || true
            echo "  Updated MEMORY.md paths to match new structure"
        fi
    else
        echo "Auto-memory directory exists but contains no .md files"
    fi

    # Remove source directory if empty
    REMAINING=$(find "$AUTO_MEMORY_DIR" -maxdepth 1 -type f | wc -l | tr -d ' ')
    if [ "$REMAINING" -eq 0 ]; then
        rm -rf "$AUTO_MEMORY_DIR"
        echo "Removed empty auto-memory directory"
    else
        echo "Warning: $REMAINING file(s) still in auto-memory dir — not removing"
    fi
elif [ -L "$AUTO_MEMORY_DIR" ]; then
    CURRENT_TARGET=$(readlink "$AUTO_MEMORY_DIR")
    if [ "$CURRENT_TARGET" = "$SERENA_MEMORY_DIR" ]; then
        echo "Symlink already exists and points to correct target"
    else
        echo "Symlink exists but points to: $CURRENT_TARGET"
        echo "Updating to: $SERENA_MEMORY_DIR"
        rm "$AUTO_MEMORY_DIR"
    fi
else
    echo "No existing auto-memory directory — clean setup"
fi
```

### Step 4: Create Symlink

```bash
if [ ! -L "$AUTO_MEMORY_DIR" ]; then
    # Ensure parent directory exists
    mkdir -p "$(dirname "$AUTO_MEMORY_DIR")"
    ln -s "$SERENA_MEMORY_DIR" "$AUTO_MEMORY_DIR"
    echo "Created symlink: $AUTO_MEMORY_DIR -> $SERENA_MEMORY_DIR"
fi
```

### Step 5: Update memory-paths.conf

```bash
MEMORY_PATHS_CONF=".serena/memory-paths.conf"
if [ -f "$MEMORY_PATHS_CONF" ]; then
    if ! grep -q '^\./\.serena/memory$' "$MEMORY_PATHS_CONF"; then
        echo './.serena/memory' >> "$MEMORY_PATHS_CONF"
        echo "Added ./.serena/memory to memory-paths.conf"
    else
        echo "./.serena/memory already in memory-paths.conf"
    fi
else
    echo "Warning: memory-paths.conf not found — run /swe-init first"
fi
```

### Step 6: Add CLAUDE.md Directives

Check CLAUDE.md for the auto-memory directive block. If not present, add it:

```markdown
## Auto-Memory Symlink

This project uses a symlink to redirect Claude Code's auto-memory into `.serena/memory/`.

- Use `write_memory()` for all memory operations (not the Write tool)
- Update MEMORY.md index when adding new memories
- Never write directly to `~/.claude/projects/.../memory/`
```

Only add if the `## Auto-Memory Symlink` heading is not already present in CLAUDE.md.

### Step 7: Verify

```bash
if [ -L "$AUTO_MEMORY_DIR" ] && [ "$(readlink "$AUTO_MEMORY_DIR")" = "$SERENA_MEMORY_DIR" ]; then
    echo "Symlink OK: $AUTO_MEMORY_DIR -> $SERENA_MEMORY_DIR"

    # Write test
    echo "test" > "$AUTO_MEMORY_DIR/.symlink-test"
    if [ -f "$SERENA_MEMORY_DIR/.symlink-test" ]; then
        echo "Write-through OK"
        rm "$SERENA_MEMORY_DIR/.symlink-test"
    else
        echo "ERROR: Write-through failed"
    fi
else
    echo "ERROR: Symlink not configured correctly"
fi
```

## Output

```
**AUTO-MEMORY SYMLINK CONFIGURED**

- Symlink: ~/.claude/projects/<encoded>/memory -> .serena/memory/
- memory-paths.conf: Updated
- CLAUDE.md: Directives added
- Write-through: Verified
```
