#!/usr/bin/env python3
"""
Example usage of the Claude Memory System
This script demonstrates how to use the memory tracking utilities
"""

from utils.claude_memory import ClaudeMemory

def main():
    # Initialize the memory system
    memory = ClaudeMemory()
    
    # Example: Start a new session
    session_id = "2025-01-21_example"
    memory.start_session(session_id, "Example session demonstrating memory system")
    
    # Example: Log some edits
    memory.log_edit(session_id, "example_file.py", "create", "Created example file", 50)
    memory.log_edit(session_id, "config/settings.json", "modify", "Updated configuration", 3)
    memory.log_edit(session_id, "utils/helper.py", "modify", "Fixed bug in helper function", 12)
    
    # Example: Add some tasks
    memory.add_task("example_001", session_id, "Create example documentation", "medium", "pending")
    memory.add_task("example_002", session_id, "Test the memory system", "high", "in_progress")
    
    # Example: Complete a task
    memory.complete_task("example_002")
    
    # Example: Get session summary
    summary = memory.generate_session_summary(session_id)
    print("Session Summary:")
    print(f"  Session ID: {summary['session_id']}")
    print(f"  Total Edits: {summary['total_edits']}")
    print(f"  Files Modified: {summary['files_modified']}")
    print(f"  Total Lines Changed: {summary['total_lines_changed']}")
    print(f"  Edit Types: {summary['edit_types']}")
    print(f"  Files: {', '.join(summary['files'])}")
    
    # Example: Get recent sessions
    recent = memory.get_recent_sessions(3)
    print(f"\nRecent Sessions: {len(recent)} found")
    for session in recent:
        print(f"  {session['session_id']}: {session['task_description']} [{session['status']}]")
    
    # Example: Get active tasks
    active_tasks = memory.get_active_tasks()
    print(f"\nActive Tasks: {len(active_tasks)} found")
    for task in active_tasks:
        print(f"  {task['task_id']}: {task['description']} [{task['status']}]")
    
    # End the session
    memory.end_session(session_id)
    print(f"\nSession {session_id} completed!")

if __name__ == "__main__":
    main()