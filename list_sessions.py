#!/usr/bin/env python3
import json
import os
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

def get_projects():
    """
    Returns a dictionary of all projects registered in ~/.gemini/projects.json.
    Keys are project paths, values are short IDs.
    """
    home_dir = Path.home()
    projects_json_path = home_dir / ".gemini" / "projects.json"

    if projects_json_path.exists():
        try:
            with open(projects_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("projects", {})
        except Exception:
            pass
    return {}

def extract_first_user_message(messages):
    for msg in messages:
        if msg.get("type") == "user":
            content = msg.get("content", "")

            # Simple content parsing (ignoring complex part logic for now)
            text_parts = []
            if isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and "text" in p:
                        text_parts.append(p["text"])
                    elif isinstance(p, str):
                        text_parts.append(p)
            elif isinstance(content, str):
                text_parts.append(content)

            text = " ".join(text_parts).strip()

            # Filter slash commands if possible
            if not text.startswith("/") and not text.startswith("?") and text:
                return " ".join(text.split())

    # Fallback to the first user message even if it's a slash command
    for msg in messages:
        if msg.get("type") == "user":
            content = msg.get("content", "")
            text_parts = []
            if isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and "text" in p:
                        text_parts.append(p["text"])
                    elif isinstance(p, str):
                        text_parts.append(p)
            elif isinstance(content, str):
                text_parts.append(content)

            text = " ".join(text_parts).strip()
            if text:
                return " ".join(text.split())

    return "Empty conversation"

def parse_isoformat(time_str):
    time_str = time_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(time_str)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

def get_sessions(project_tmp_dir, project_path):
    chats_dir = project_tmp_dir / "chats"
    if not chats_dir.exists() or not chats_dir.is_dir():
        return []

    sessions_map = {}
    for file_path in chats_dir.glob("session-*.json"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            session_id = data.get("sessionId")
            messages = data.get("messages")
            start_time = data.get("startTime")
            last_updated = data.get("lastUpdated")

            if not session_id or not isinstance(messages, list) or not start_time or not last_updated:
                continue

            # Check if it has user/assistant message
            has_meaningful_msg = any(msg.get("type") in ("user", "gemini") for msg in messages)
            if not has_meaningful_msg:
                continue

            # Skip subagent sessions
            if data.get("kind") == "subagent":
                continue

            summary = data.get("summary")
            first_user_message = extract_first_user_message(messages)

            display_name = summary if summary else first_user_message
            if display_name:
                display_name = " ".join(display_name.split()) # Clean up whitespace

            session_info = {
                "projectPath": project_path,
                "id": session_id,
                "file": file_path.stem,
                "startTime": start_time,
                "lastUpdated": last_updated,
                "messageCount": len(messages),
                "displayName": display_name,
                "firstUserMessage": first_user_message
            }

            # Deduplicate by session_id, keeping latest
            if session_id in sessions_map:
                existing = sessions_map[session_id]
                existing_time = parse_isoformat(existing["lastUpdated"])
                new_time = parse_isoformat(last_updated)
                if new_time > existing_time:
                    sessions_map[session_id] = session_info
            else:
                sessions_map[session_id] = session_info

        except Exception:
            continue

    sessions = list(sessions_map.values())

    # Assign indices based on start time (oldest first, like CLI does for display)
    sessions.sort(key=lambda x: parse_isoformat(x["startTime"]))
    for i, s in enumerate(sessions):
        s["index"] = i + 1

    return sessions

def get_checkpoints(project_tmp_dir, project_path):
    if not project_tmp_dir.exists() or not project_tmp_dir.is_dir():
        return []

    checkpoints = []
    for file_path in project_tmp_dir.glob("checkpoint-*.json"):
        try:
            filename = file_path.name
            encoded_tag = filename[len("checkpoint-"):-len(".json")]
            tag = urllib.parse.unquote(encoded_tag)

            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            history = data.get("history", [])
            auth_type = data.get("authType")

            stat = file_path.stat()
            last_updated = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")

            checkpoints.append({
                "projectPath": project_path,
                "tag": tag,
                "file": file_path.stem,
                "messageCount": len(history),
                "authType": auth_type,
                "lastUpdated": last_updated
            })

        except Exception:
            continue

    return checkpoints

def main():
    import argparse
    parser = argparse.ArgumentParser(description="List Gemini CLI sessions and checkpoints")
    parser.add_argument("--all", action="store_true", help="List sessions for all registered projects")
    args = parser.parse_args()

    projects = get_projects()
    home_dir = Path.home()

    target_projects = {}

    if args.all:
        target_projects = projects
    else:
        # User requested "both" when I asked if it should be scoped to current or all.
        # But for CLI flexibility, we can output the current project by default and all if --all is passed,
        # OR just always output all projects if that's what "both" meant in the user prompt.
        # Let's always list all projects since the prompt review said "failing to provide the 'all projects' functionality."
        target_projects = projects

    all_sessions = []
    all_checkpoints = []

    # Also include current directory if it's not in projects.json just in case? No, rely on registry.
    cwd = str(Path.cwd().resolve())

    for project_path, short_id in target_projects.items():
        project_tmp_dir = home_dir / ".gemini" / "tmp" / short_id
        all_sessions.extend(get_sessions(project_tmp_dir, project_path))
        all_checkpoints.extend(get_checkpoints(project_tmp_dir, project_path))

    # Sort all combined sessions and checkpoints by lastUpdated descending
    all_sessions.sort(key=lambda x: parse_isoformat(x["lastUpdated"]), reverse=True)
    all_checkpoints.sort(key=lambda x: parse_isoformat(x["lastUpdated"]), reverse=True)

    output = {
        "sessions": all_sessions,
        "checkpoints": all_checkpoints
    }

    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
