# Claude Code ToolBox — Intelligence readiness

Run commands from the Command Palette (`Claude Code ToolBox: …`) or the **MCP & skills** hub.

## ✓ claude-md
`CLAUDE.md` looks populated.

Suggested: `CloudeCodeToolBox.openInstructionsPicker`

## ✓ claude-rules
No `.claude/rules/*.md` files (optional scoped rules).

Suggested: `CloudeCodeToolBox.syncCursorRules`

## ✓ agents-md
No `AGENTS.md` (optional agent-oriented instructions).

Suggested: `CloudeCodeToolBox.openInstructionsPicker`

## ✓ memory-bank
`memory-bank/` directory present.

Suggested: `CloudeCodeToolBox.initMemoryBank`

## ○ mcp-json
Workspace `.mcp.json` missing — port from Cursor or add servers via the MCP tab.

Suggested: `CloudeCodeToolBox.portCursorMcp`

## ○ cursorrules
No `.cursorrules` or `.cursor/rules` files detected.

Suggested: `CloudeCodeToolBox.createCursorrulesTemplate`

## ✓ copilot-instructions-legacy
No `.github/copilot-instructions.md` (legacy GitHub Copilot instructions).

Suggested: `CloudeCodeToolBox.mergeCopilotInstructionsIntoClaudeMd`

## ✓ mcp-claude-user
Claude Code user MCP lives in **`~/.claude.json`** (`mcpServers` key). Use the MCP hub tab or `claude mcp add` to manage servers.

Suggested: `CloudeCodeToolBox.openUserMcp`
