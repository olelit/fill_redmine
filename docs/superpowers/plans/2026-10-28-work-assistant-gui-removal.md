# Work Assistant GUI Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to implement this plan after MCP verification. This repository requires a fresh subagent per task and review between tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Tkinter GUI and its launch/install paths after the MCP workflows are working and verified.

**Architecture:** Keep the new MCP server and reusable tracker/client code as the only supported interface. Delete GUI-only modules and tests, update the project instructions, and leave user data and legacy storage files untouched.

**Tech Stack:** Python 3.10+, MCP Python SDK v2, pytest, existing tracker clients and MCP tests.

## Global Constraints

- Do not start this plan until `2026-10-28-work-assistant-mcp.md` passes its tests and MCP flows have been checked.
- MCP stdio remains the only supported user interface after this plan.
- Preserve `.env`, ignored `config/users.json`, `work_assistant.db`, `fill_redmine.db`, `user_list.py.migrated`, and all other local user data.
- Keep tracker clients/services and all tests needed by MCP; remove only GUI-specific modules and tests.
- Do not delete embedded AI or SQLite backend modules in this cleanup; that is separate scope and requires reference/test review.

---

## Task 1: Remove GUI code and document MCP-only operation

**Files:**
- Delete: `gui/`
- Delete: `work_assistant.py`
- Delete: `fill_redmine_gui.py`
- Delete: `run_gui.sh`
- Delete: `Work Assistant.desktop`
- Delete: `scripts/install_desktop.sh`
- Delete: `assets/work_assistant.svg`
- Delete GUI-only tests: `tests/test_gui_worker.py`, `tests/test_gui_validation.py`, `tests/test_gui_formatting.py`, `tests/test_report_editor_validation.py`, `tests/test_settings_validation.py`, `tests/test_tracking_validation.py`, `tests/test_ai_settings_validation.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `.env.example`

**Interfaces:**
- `python -m mcp_server` remains the configured local MCP entry point.
- Existing tracker/service tests remain; no module imported by the MCP server is deleted.
- The ignored database and legacy files remain byte-for-byte untouched.

- [ ] **Step 1: Verify MCP is green before removal**

Run: `pytest -q`  
Expected: PASS before deleting the GUI. If it fails, stop and fix the MCP plan first.

- [ ] **Step 2: Remove GUI-only runtime and launcher files**

Delete the exact GUI directories, entry points, launchers, desktop asset, and GUI-only tests listed above. Before deleting `scripts/` or `assets/`, confirm each contains only the listed GUI file; retain the directory if another tracked file exists.

- [ ] **Step 3: Rewrite user and contributor documentation for MCP-only operation**

Update `README.md` with the MCP setup, ignored JSON config, tracker URL env vars, available tools, missing Redmine issue-ID prompt, strict elicitation approval, and the rule that the agent provides AI analysis. Remove GUI launch, desktop installation, and Tkinter instructions. Update `AGENTS.md` project overview and run/test commands to point to the MCP server and pytest. Remove `WORK_ASSISTANT_DB` from `.env.example` because MCP does not read the SQLite database; do not change any user's actual `.env` or database.

- [ ] **Step 4: Audit references and run the complete test suite**

Run: `rg -n "work_assistant\.py|fill_redmine_gui|run_gui\.sh|Tkinter|tkinter|install_desktop|Work Assistant\.desktop|from gui|import gui" README.md AGENTS.md .env.example mcp_server tests`  
Expected: no matches (ripgrep exit status 1). Also verify `test ! -e gui`, `test ! -e work_assistant.py`, and `test ! -e fill_redmine_gui.py` each exits 0. Then run `pytest -q`; expected: all backend and MCP tests pass. Run `git diff --check`; expected: no output.

- [ ] **Step 5: Commit the GUI removal**

Commit only the GUI deletion and documentation changes as `refactor: remove GUI and make MCP the only interface`.
