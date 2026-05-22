---
name: swe-sym-link
description: Set up auto-memory symlink to redirect Claude Code memory into project repo
---

# /swe-sym-link

Replace Claude Code's auto-memory directory with a symlink pointing to the project's `.serena/memory/` directory. This unifies auto-memory with Serena's memory system and makes memory files version-controllable.

## When to Run

- During `/swe-init` (included as Task 10)
- Standalone after cloning a repo that already uses SWE
- When setting up a new machine for an existing SWE project

## Process

### Step 1: Determine Paths

```bash
PROJECT_PATH=$(pwd)
ENCODED_PATH=$(echo "$PROJECT_PATH" | sed 's|/|-|g')
AUTO_MEMORY_DIR="$HOME/.claude/projects/$ENCODED_PATH/memory"
SERENA_MEMORY_DIR="$PROJECT_PATH/.serena/memory"

echo "Auto-memory path: $AUTO_MEMORY_DIR"
echo "Serena memory target: $SERENA_MEMORY_DIR"
```

### Step 2: Ensure Target Directory Exists

```bash
mkdir -p "$SERENA_MEMORY_DIR"
```

### Step 3: Migrate Existing Auto-Memory Content

```bash
if [ -d "$AUTO_MEMORY_DIR" ] && [ ! -L "$AUTO_MEMORY_DIR" ]; then
    # Check for actual files (not just an empty directory)
    FILE_COUNT=$(find "$AUTO_MEMORY_DIR" -maxdepth 1 -type f | wc -l | tr -d ' ')
    if [ "$FILE_COUNT" -gt 0 ]; then
        echo "Found $FILE_COUNT file(s) in auto-memory directory — migrating..."
        for f in "$AUTO_MEMORY_DIR"/*; do
            [ -f "$f" ] || continue
            basename=$(basename "$f")
            if [ ! -f "$SERENA_MEMORY_DIR/$basename" ]; then
                cp "$f" "$SERENA_MEMORY_DIR/$basename"
                echo "  Migrated: $basename"
            else
                echo "  Skipped (already exists in target): $basename"
            fi
        done
    else
        echo "Auto-memory directory exists but contains no files"
    fi
    # Verify no files remain before removing
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
