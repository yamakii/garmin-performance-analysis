# garmin-mcp-server

MCP server for the Garmin running performance analysis system: ingests Garmin
Connect data into DuckDB (22+ normalized tables) and exposes token-optimized
analysis tools via a single-source `tools/` registry.

See the [repository README](../../README.md) and `CLAUDE.md` at the repo root
for architecture, workflows, and the full tool reference
(`docs/mcp-tools-reference.md`).
