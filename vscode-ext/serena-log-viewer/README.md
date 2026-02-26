# SWE: Serena Log Viewer

Tails Serena MCP server logs into the VSCode Output panel in real-time.

## Features

- Creates an **"SWE: Serena Logs"** output channel in the Output panel
- Automatically finds and tails the latest `mcp_*.txt` log file
- Switches to new log files as Serena starts new sessions
- Handles day rollovers at midnight
- Zero dependencies

## Usage

1. Open the **Output** panel (View > Output)
2. Select **"SWE: Serena Logs"** from the dropdown
3. Or run `Cmd+Shift+P` > **"SWE: Show Serena Logs"**

## Installation

Installed automatically by `/swe-init` (Task 12). To install manually:

```bash
ln -s /absolute/path/to/.claude/plugins/serena-workflow-engine/vscode-ext/serena-log-viewer \
  ~/.vscode/extensions/serena-log-viewer
```

Then reload VSCode (`Cmd+Shift+P` > "Developer: Reload Window").

## Log Location

Serena writes logs to `~/.serena/logs/<YYYY-MM-DD>/mcp_<timestamp>.txt`.

Set the `SERENA_HOME` environment variable to override the default `~/.serena` directory.

## Uninstall

```bash
rm ~/.vscode/extensions/serena-log-viewer
```
