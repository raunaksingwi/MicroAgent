# Available Tools

This document describes the tools available to nanobot.

## File Operations

### read_file
Read the contents of a file.
```
read_file(path: str) -> str
```

### write_file
Write content to a file (creates parent directories if needed).
```
write_file(path: str, content: str) -> str
```

### edit_file
Edit a file by replacing specific text.
```
edit_file(path: str, old_text: str, new_text: str) -> str
```

### list_dir
List contents of a directory.
```
list_dir(path: str) -> str
```

## Shell Execution

### exec
Execute a shell command and return output.
```
exec(command: str, working_dir: str = None) -> str
```

**Safety Notes:**
- Commands have a configurable timeout (default 60s)
- Dangerous commands are blocked (rm -rf, format, dd, shutdown, etc.)
- Output is truncated at 10,000 characters
- Optional `restrictToWorkspace` config to limit paths

## Web Access

### web_search
Search the web using Brave Search API.
```
web_search(query: str, count: int = 5) -> str
```

Returns search results with titles, URLs, and snippets. Requires `tools.web.search.apiKey` in config.

### web_fetch
Fetch and extract main content from a URL.
```
web_fetch(url: str, extractMode: str = "markdown", maxChars: int = 50000) -> str
```

**Notes:**
- Content is extracted using readability
- Supports markdown or plain text extraction
- Output is truncated at 50,000 characters by default

## Communication

### message
Send a message to the user (used internally).
```
message(content: str, channel: str = None, chat_id: str = None) -> str
```

## Background Tasks

### spawn
Spawn a subagent to handle a task in the background.
```
spawn(task: str, label: str = None) -> str
```

Use for complex or time-consuming tasks that can run independently. The subagent will complete the task and report back when done.

## Scheduled Reminders (Cron)

Use the `exec` tool to create scheduled reminders with `nanobot cron add`:

### Set a recurring reminder
```bash
# Every day at 9am
nanobot cron add --name "morning" --message "Good morning! ☀️" --cron "0 9 * * *"

# Every 2 hours
nanobot cron add --name "water" --message "Drink water! 💧" --every 7200
```

### Set a one-time reminder
```bash
# At a specific time (ISO format)
nanobot cron add --name "meeting" --message "Meeting starts now!" --at "2025-01-31T15:00:00"
```

### Manage reminders
```bash
nanobot cron list              # List all jobs
nanobot cron remove <job_id>   # Remove a job
```

## Heartbeat Task Management

The `HEARTBEAT.md` file in the workspace is checked every 30 minutes.
Use file operations to manage periodic tasks:

### Add a heartbeat task
```python
# Append a new task
edit_file(
    path="HEARTBEAT.md",
    old_text="## Example Tasks",
    new_text="- [ ] New periodic task here\n\n## Example Tasks"
)
```

### Remove a heartbeat task
```python
# Remove a specific task
edit_file(
    path="HEARTBEAT.md",
    old_text="- [ ] Task to remove\n",
    new_text=""
)
```

### Rewrite all tasks
```python
# Replace the entire file
write_file(
    path="HEARTBEAT.md",
    content="# Heartbeat Tasks\n\n- [ ] Task 1\n- [ ] Task 2\n"
)
```

## Sunday Identity (Digital Identity Management)

### sunday
Manage your Sunday digital identity — passwords, email inbox, and identity info.
All data is end-to-end encrypted; the tool handles crypto transparently.

```
sunday(action: str, ...) -> str
```

**Actions:**

| Action | Description | Required params |
|--------|-------------|-----------------|
| `get_identity` | Show your identity name, UUID, and email | — |
| `get_master` | Show your master (owner) name and email | — |
| `list_emails` | List your Sunday email addresses | — |
| `list_inbox` | List inbox messages (email + SMS) | — |
| `get_email` | Read a specific email message | `message_id` |
| `list_passwords` | List saved credentials | — |
| `get_password` | Retrieve a specific password | `uuid` |
| `create_password` | Save a new credential | `domain` |
| `update_password` | Update an existing credential | `uuid` |
| `delete_password` | Delete a credential | `uuid` |
| `generate_password` | Generate a random password | `length` (default 16) |

**Workflow: Signing up for a new service**
1. `generate_password` — get a secure random password
2. `create_password` with the domain, generated password, and your Sunday email as username
3. Use your Sunday email (from `get_identity`) to sign up on the website
4. `list_inbox` — check for verification emails

**Examples:**
```
# Check your identity and email
sunday(action="get_identity")

# Generate a password, then save credentials
sunday(action="generate_password", length=20)
sunday(action="create_password", domain="github.com", username="me@sunday.app", password="...")

# Read inbox for verification emails
sunday(action="list_inbox")
sunday(action="get_email", message_id=42)

# Retrieve saved credentials
sunday(action="list_passwords")
sunday(action="get_password", uuid="...")
```

---

## Adding Custom Tools

To add custom tools:
1. Create a class that extends `Tool` in `nanobot/agent/tools/`
2. Implement `name`, `description`, `parameters`, and `execute`
3. Register it in `AgentLoop._register_default_tools()`
