# METU ODTUClass MCP Server

> **A Model Context Protocol (MCP) server for METU's ODTUClass learning management system** — enabling AI assistants to query courses, announcements, syllabi, assignment deadlines, and lab schedules directly from [odtuclass.metu.edu.tr](https://odtuclass.metu.edu.tr).

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP Compatible](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

---

## Overview

This server bridges your AI assistant (Antigravity IDE, Claude Desktop, or any MCP-compatible client) with ODTUClass — METU's Moodle-based learning platform. Once connected, you can ask your AI to:

- *"What courses am I enrolled in this semester?"*
- *"Show me the latest announcements from PHYS 106."*
- *"Download and summarize the syllabus for MATH 130."*
- *"What assignments are due this week?"*
- *"When is my CENG 242 Section 3 recitation?"*

---

## Available MCP Tools

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `login` | `username`, `password` | Authenticate with METU credentials and cache session token |
| `get_enrolled_courses` | `student_token?` | List all courses you are enrolled in, with IDs and links |
| `get_course_announcements` | `course_id`, `limit?`, `student_token?` | Fetch latest forum announcements for a course |
| `get_course_syllabus` | `course_id`, `student_token?` | Locate and extract syllabus PDFs or course policy pages |
| `get_upcoming_assignments` | `student_token?` | List upcoming deadlines and assignments with time remaining |
| `get_lab_recitation_info` | `course_code`, `section`, `student_token?` | Find lab/recitation time and room for a specific section |

> All `student_token` parameters are optional when credentials are configured via environment variables or `.env.local`.

---

## Authentication

Two methods are supported. **Credentials-based login is recommended** — it requires no manual token extraction.

### Option A — METU Username & Password (Recommended)

Set your credentials in `.env.local` (gitignored, never committed):

```ini
ODTUCLASS_USERNAME=e123456
ODTUCLASS_PASSWORD=your_metu_password
```

The server reads this file on startup, authenticates automatically, and securely caches the session token in `.odtuclass_cache/session.json`. Subsequent runs reuse the cached token.

You can also ask the AI to log in explicitly:
> *"Log in to ODTUClass with username `e123456` and password `...`"*

### Option B — Web Service Token (Security Key)

1. Visit [ODTUClass](https://odtuclass.metu.edu.tr) and log in.
2. Click your name in the top-right → **Preferences**.
3. Under **User Account**, open **Security keys**.
4. Copy the **Moodle mobile web service** token (32-character alphanumeric string).

Then set it in `.env.local`:
```ini
ODTUCLASS_TOKEN=your_32_character_token
```

---

## Installation

### Prerequisites
- Python 3.10 or later
- `pip` (or `uv`)

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/metu-odtuclass-mcp.git
cd metu-odtuclass-mcp
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # macOS / Linux
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Credentials

```bash
cp .env.example .env.local
# Edit .env.local with your METU username/password or token
```

---

## Client Configuration

### Antigravity IDE

Add the following to your workspace `.agents/mcp_config.json` or global `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "odtuclass": {
      "command": "/path/to/metu-odtuclass-mcp/.venv/Scripts/python.exe",
      "args": ["/path/to/metu-odtuclass-mcp/odtuclass_mcp.py"],
      "env": {
        "ODTUCLASS_BASE_URL": "https://odtuclass.metu.edu.tr"
      }
    }
  }
}
```

Credentials are loaded automatically from `.env.local` — keep them out of `mcp_config.json`.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "odtuclass": {
      "command": "/path/to/.venv/Scripts/python.exe",
      "args": ["/path/to/metu-odtuclass-mcp/odtuclass_mcp.py"]
    }
  }
}
```

---

## Selecting a Semester

ODTUClass runs on semester-specific subdomains. The server auto-discovers the active semester by following redirects from `odtuclass.metu.edu.tr`. To target a specific past semester, set `ODTUCLASS_BASE_URL`:

| Semester | URL |
| :--- | :--- |
| Current (auto-redirect) | `https://odtuclass.metu.edu.tr` |
| 2024–2025 Spring | `https://odtuclass2025s.metu.edu.tr` |
| 2024–2025 Fall | `https://odtuclass2024f.metu.edu.tr` |
| 2023–2024 Spring | `https://odtuclass2024s.metu.edu.tr` |
| 2023–2024 Fall | `https://odtuclass2023f.metu.edu.tr` |
| 2023–2024 Summer | `https://odtuclass2024sum.metu.edu.tr` |

---

## Running & Testing

### Start the MCP Server

```bash
python odtuclass_mcp.py
```

### Interactive Live Test (Multi-Semester)

```bash
python test_live.py
```

Prompts for semester selection, authenticates, and tests course listing, assignment deadlines, announcements, and syllabus fetching interactively.

### Visual MCP Inspector (Browser UI)

```bash
mcp dev odtuclass_mcp.py
```

Opens a local browser UI to browse tools and execute them with custom parameters.

### Unit Tests

```bash
python -m unittest discover tests -v
```

---

## Project Structure

```
metu-odtuclass-mcp/
├── odtuclass_mcp.py          # MCP server definition and tool handlers
├── odtuclass_client.py       # ODTUClass Moodle REST API client
│                             #   · Semester auto-discovery
│                             #   · Credential-based login
│                             #   · Secure session token caching
│                             #   · File download management
├── models.py                 # Pydantic data models and type definitions
├── requirements.txt          # Runtime dependencies
├── pyproject.toml            # Package configuration
├── test_live.py              # Interactive multi-semester live test script
├── .env.example              # Environment variable template (safe to commit)
├── .env.local                # Your local credentials (gitignored)
├── .odtuclass_cache/         # Session token cache (gitignored)
├── downloads/                # Downloaded course files (gitignored)
└── tests/
    ├── __init__.py
    └── test_odtuclass.py     # Unit and mock test suite (21 tests)
```

---

## Security Notes

| File / Folder | Committed to Git? | Purpose |
| :--- | :---: | :--- |
| `.env.local` | ❌ No | Your local credentials and token |
| `.env.example` | ✅ Yes | Template showing required variables |
| `.odtuclass_cache/` | ❌ No | Cached session token (token only, never password) |
| `downloads/` | ❌ No | Downloaded syllabi and course files |
| `.agents/mcp_config.json` | ✅ Yes (no secrets) | Server path and base URL only |

> **Never** put your METU password directly in `mcp_config.json` or any committed file. Use `.env.local` instead.

---

## License

This project is licensed under the terms of the [MIT License](./LICENSE).