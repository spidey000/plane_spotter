"""
Claude Memory System - CSV-based tracking for project edits and sessions
This module provides utilities for tracking Claude's work sessions and file changes
"""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

class ClaudeMemory:
    """Manages Claude's memory system using CSV files for tracking sessions, edits, files, and tasks."""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.sessions_file = self.project_root / "claude_memory_sessions.csv"
        self.edits_file = self.project_root / "claude_memory_edits.csv"
        self.files_file = self.project_root / "claude_memory_files.csv"
        self.tasks_file = self.project_root / "claude_memory_tasks.csv"
        
        self._ensure_files_exist()
    
    def _ensure_files_exist(self):
        """Ensure all memory CSV files exist with proper headers"""
        
        # Sessions file
        if not self.sessions_file.exists():
            with open(self.sessions_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['session_id', 'start_time', 'end_time', 'task_description', 'status', 'files_count'])
        
        # Edits file
        if not self.edits_file.exists():
            with open(self.edits_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['timestamp', 'session_id', 'file_path', 'edit_type', 'description', 'git_commit', 'lines_changed'])
        
        # Files file
        if not self.files_file.exists():
            with open(self.files_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['file_path', 'last_modified', 'file_size', 'last_session', 'current_status', 'notes'])
        
        # Tasks file
        if not self.tasks_file.exists():
            with open(self.tasks_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['task_id', 'session_id', 'description', 'status', 'priority', 'created_at', 'completed_at'])
    
    def start_session(self, session_id: str, task_description: str) -> None:
        """Start a new session"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(self.sessions_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([session_id, timestamp, '', task_description, 'in_progress', 0])
    
    def end_session(self, session_id: str) -> None:
        """End a session by updating its end_time and status"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Read all sessions
        sessions = []
        with open(self.sessions_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            sessions = list(reader)
        
        # Update the target session
        for session in sessions:
            if session['session_id'] == session_id:
                session['end_time'] = timestamp
                session['status'] = 'completed'
                break
        
        # Write back to file
        with open(self.sessions_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['session_id', 'start_time', 'end_time', 'task_description', 'status', 'files_count']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(sessions)
    
    def log_edit(self, session_id: str, file_path: str, edit_type: str, 
                 description: str, lines_changed: int = 0, git_commit: str = '') -> None:
        """Log a file edit"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(self.edits_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, session_id, file_path, edit_type, description, git_commit, lines_changed])
        
        # Update file tracking
        self.update_file_status(file_path, session_id, edit_type, description)
    
    def update_file_status(self, file_path: str, session_id: str, status: str, notes: str = '') -> None:
        """Update or add file status tracking"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Get file size if it exists
        file_size = 0
        full_path = self.project_root / file_path
        if full_path.exists():
            file_size = full_path.stat().st_size
        
        # Read current file states
        files = []
        try:
            with open(self.files_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                files = list(reader)
        except FileNotFoundError:
            pass
        
        # Update or add file entry
        file_found = False
        for file_entry in files:
            if file_entry['file_path'] == file_path:
                file_entry['last_modified'] = timestamp
                file_entry['file_size'] = str(file_size)
                file_entry['last_session'] = session_id
                file_entry['current_status'] = status
                file_entry['notes'] = notes
                file_found = True
                break
        
        if not file_found:
            files.append({
                'file_path': file_path,
                'last_modified': timestamp,
                'file_size': str(file_size),
                'last_session': session_id,
                'current_status': status,
                'notes': notes
            })
        
        # Write back to file
        with open(self.files_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['file_path', 'last_modified', 'file_size', 'last_session', 'current_status', 'notes']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(files)
    
    def add_task(self, task_id: str, session_id: str, description: str, 
                 priority: str = 'medium', status: str = 'pending') -> None:
        """Add a new task"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(self.tasks_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([task_id, session_id, description, status, priority, timestamp, ''])
    
    def complete_task(self, task_id: str) -> None:
        """Mark a task as completed"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Read all tasks
        tasks = []
        with open(self.tasks_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            tasks = list(reader)
        
        # Update the target task
        for task in tasks:
            if task['task_id'] == task_id:
                task['status'] = 'completed'
                task['completed_at'] = timestamp
                break
        
        # Write back to file
        with open(self.tasks_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['task_id', 'session_id', 'description', 'status', 'priority', 'created_at', 'completed_at']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(tasks)
    
    def get_recent_sessions(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent sessions"""
        try:
            with open(self.sessions_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                sessions = list(reader)
                return sessions[-limit:] if sessions else []
        except FileNotFoundError:
            return []
    
    def get_session_edits(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all edits for a specific session"""
        try:
            with open(self.edits_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return [edit for edit in reader if edit['session_id'] == session_id]
        except FileNotFoundError:
            return []
    
    def get_file_history(self, file_path: str) -> List[Dict[str, Any]]:
        """Get edit history for a specific file"""
        try:
            with open(self.edits_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return [edit for edit in reader if edit['file_path'] == file_path]
        except FileNotFoundError:
            return []
    
    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Get all pending and in-progress tasks"""
        try:
            with open(self.tasks_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return [task for task in reader if task['status'] in ['pending', 'in_progress']]
        except FileNotFoundError:
            return []
    
    def generate_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Generate a summary for a specific session"""
        edits = self.get_session_edits(session_id)
        
        files_modified = len(set(edit['file_path'] for edit in edits))
        total_lines_changed = sum(int(edit['lines_changed']) for edit in edits if edit['lines_changed'].isdigit())
        
        edit_types = {}
        for edit in edits:
            edit_type = edit['edit_type']
            edit_types[edit_type] = edit_types.get(edit_type, 0) + 1
        
        return {
            'session_id': session_id,
            'total_edits': len(edits),
            'files_modified': files_modified,
            'total_lines_changed': total_lines_changed,
            'edit_types': edit_types,
            'files': [edit['file_path'] for edit in edits]
        }

# Convenience functions for easy use
def init_memory_system(project_root: str = ".") -> ClaudeMemory:
    """Initialize the Claude memory system"""
    return ClaudeMemory(project_root)

def log_quick_edit(file_path: str, description: str, session_id: str = "quick_edit", 
                   edit_type: str = "modify", lines_changed: int = 0) -> None:
    """Quick function to log an edit"""
    memory = ClaudeMemory()
    memory.log_edit(session_id, file_path, edit_type, description, lines_changed)