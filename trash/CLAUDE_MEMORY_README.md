# Claude Memory System

A CSV-based memory system for tracking Claude's edits, sessions, and project versioning. This system provides structured, queryable memory storage while remaining simple and accessible.

## Overview

The memory system consists of 4 CSV files that track different aspects of Claude's work:

1. **`claude_memory_sessions.csv`** - Session tracking
2. **`claude_memory_edits.csv`** - File edit history  
3. **`claude_memory_files.csv`** - File state tracking
4. **`claude_memory_tasks.csv`** - Task/todo tracking

## File Structure

### Sessions File (`claude_memory_sessions.csv`)
Tracks work sessions with start/end times and descriptions.

**Columns:**
- `session_id` - Unique identifier (e.g., "2025-01-21_bugfix")
- `start_time` - Session start timestamp
- `end_time` - Session end timestamp (empty if ongoing)
- `task_description` - Brief description of session goals
- `status` - "in_progress" or "completed"
- `files_count` - Number of files modified in session

### Edits File (`claude_memory_edits.csv`)
Chronological record of all file changes.

**Columns:**
- `timestamp` - When the edit was made
- `session_id` - Associated session
- `file_path` - Relative path to the modified file
- `edit_type` - "create", "modify", "delete", "rename"
- `description` - Brief description of changes made
- `git_commit` - Git commit hash (if available)
- `lines_changed` - Approximate number of lines modified

### Files File (`claude_memory_files.csv`)
Current state of all tracked files.

**Columns:**
- `file_path` - Relative path to the file
- `last_modified` - Last modification timestamp
- `file_size` - Current file size in bytes
- `last_session` - Session that last modified this file
- `current_status` - "created", "modified", "unchanged", "deleted"
- `notes` - Additional notes about the file

### Tasks File (`claude_memory_tasks.csv`)
Project tasks and completion tracking.

**Columns:**
- `task_id` - Unique task identifier
- `session_id` - Associated session
- `description` - Task description
- `status` - "pending", "in_progress", "completed"
- `priority` - "low", "medium", "high"
- `created_at` - Task creation timestamp
- `completed_at` - Task completion timestamp (empty if not completed)

## Usage

### Using the Python API

```python
from utils.claude_memory import ClaudeMemory

# Initialize the memory system
memory = ClaudeMemory()

# Start a new session
session_id = "2025-01-21_feature"
memory.start_session(session_id, "Implementing new feature")

# Log edits
memory.log_edit(session_id, "src/main.py", "modify", "Added new function", 25)
memory.log_edit(session_id, "tests/test_main.py", "create", "Added unit tests", 45)

# Add tasks
memory.add_task("task_001", session_id, "Write documentation", "medium")
memory.add_task("task_002", session_id, "Add error handling", "high", "in_progress")

# Complete tasks
memory.complete_task("task_002")

# Get session summary
summary = memory.generate_session_summary(session_id)
print(f"Modified {summary['files_modified']} files with {summary['total_edits']} edits")

# End session
memory.end_session(session_id)
```

### Quick Logging

```python
from utils.claude_memory import log_quick_edit

# Quick way to log a single edit
log_quick_edit("config.json", "Updated API endpoint", "maintenance", "modify", 3)
```

### Querying the System

```python
# Get recent sessions
recent_sessions = memory.get_recent_sessions(5)

# Get all edits for a session
session_edits = memory.get_session_edits("2025-01-21_bugfix")

# Get history for a specific file
file_history = memory.get_file_history("main.py")

# Get active (pending/in-progress) tasks
active_tasks = memory.get_active_tasks()
```

## Benefits

### ✅ **Machine Readable**
- CSV format is easily parsed by any programming language
- Simple structure for automated processing
- Can be imported into databases or analytics tools

### ✅ **Human Accessible**
- Files can be opened in Excel, Google Sheets, or any text editor
- Easy to scan and search manually
- No special tools required to view data

### ✅ **Lightweight**
- Small file sizes, even with extensive history
- Fast read/write operations
- Minimal dependencies (just Python stdlib)

### ✅ **Version Control Friendly**
- Plain text files work well with git
- Easy to see changes in diffs
- Can track the memory system itself

### ✅ **Queryable**
- Filter by session, file, task status, etc.
- Analyze patterns in coding sessions
- Generate reports on productivity

### ✅ **Append-Only**
- New entries are just appended to files
- No complex database operations
- Concurrent access is generally safe

## File Locations

The memory files are stored in the project root:
- `claude_memory_sessions.csv`
- `claude_memory_edits.csv`
- `claude_memory_files.csv`
- `claude_memory_tasks.csv`

These files are automatically added to `.gitignore` and `.dockerignore` to prevent accidental commits of local development history.

## Example Queries

### Find all Python files modified in the last session
```python
edits = memory.get_session_edits("2025-01-21_bugfix")
python_files = [edit['file_path'] for edit in edits if edit['file_path'].endswith('.py')]
```

### Get all high-priority pending tasks
```python
tasks = memory.get_active_tasks()
high_priority = [task for task in tasks if task['priority'] == 'high' and task['status'] == 'pending']
```

### Find files that haven't been touched recently
```python
import csv
from datetime import datetime, timedelta

cutoff = datetime.now() - timedelta(days=30)
with open('claude_memory_files.csv', 'r') as f:
    reader = csv.DictReader(f)
    old_files = [
        row for row in reader 
        if datetime.strptime(row['last_modified'], '%Y-%m-%d %H:%M:%S') < cutoff
    ]
```

## Integration with Development Workflow

The memory system can be integrated into development workflows:

1. **Session Management**: Start/end sessions for different work phases
2. **Automatic Logging**: Log edits as part of file operations
3. **Task Tracking**: Use instead of or alongside other task management tools
4. **Code Review**: Reference edit history during reviews
5. **Documentation**: Generate change logs from edit history

## Maintenance

The CSV files are designed to be self-maintaining:
- Old entries can be archived by moving to separate files
- Files can be compacted by removing old sessions
- Duplicate entries can be detected and cleaned up
- File integrity can be verified by checking CSV structure

## Future Enhancements

Potential improvements to the system:
- Automatic git integration for commit tracking
- Web interface for browsing history
- Integration with IDE plugins
- Automated backup and archiving
- Advanced analytics and reporting
- Export to other formats (JSON, SQLite, etc.)