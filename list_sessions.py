#!/usr/bin/env python3
import json
import os
import urllib.parse
import argparse
from datetime import datetime, timezone
from pathlib import Path
import math

def get_projects():
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

            if not text.startswith("/") and not text.startswith("?") and text:
                return " ".join(text.split())

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

def format_relative_time(timestamp, style='long'):
    now = datetime.now(timezone.utc)
    time = parse_isoformat(timestamp)
    diff_ms = (now - time).total_seconds() * 1000

    diff_seconds = math.floor(diff_ms / 1000)
    diff_minutes = math.floor(diff_seconds / 60)
    diff_hours = math.floor(diff_minutes / 60)
    diff_days = math.floor(diff_hours / 24)

    if style == 'short':
        if diff_seconds < 1: return 'now'
        if diff_seconds < 60: return f"{diff_seconds}s"
        if diff_minutes < 60: return f"{diff_minutes}m"
        if diff_hours < 24: return f"{diff_hours}h"
        if diff_days < 30: return f"{diff_days}d"
        diff_months = math.floor(diff_days / 30)
        return f"{diff_months}mo" if diff_months < 12 else f"{math.floor(diff_months / 12)}y"
    else:
        if diff_days > 0:
            return f"{diff_days} day{'s' if diff_days != 1 else ''} ago"
        elif diff_hours > 0:
            return f"{diff_hours} hour{'s' if diff_hours != 1 else ''} ago"
        elif diff_minutes > 0:
            return f"{diff_minutes} minute{'s' if diff_minutes != 1 else ''} ago"
        else:
            return 'Just now'

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

            has_meaningful_msg = any(msg.get("type") in ("user", "gemini") for msg in messages)
            if not has_meaningful_msg:
                continue

            if data.get("kind") == "subagent":
                continue

            summary = data.get("summary")
            first_user_message = extract_first_user_message(messages)

            display_name = summary if summary else first_user_message
            if display_name:
                display_name = " ".join(display_name.split())

            session_info = {
                "projectPath": project_path,
                "absolutePath": str(file_path.resolve()),
                "id": session_id,
                "file": file_path.stem,
                "startTime": start_time,
                "lastUpdated": last_updated,
                "messageCount": len(messages),
                "displayName": display_name,
                "firstUserMessage": first_user_message,
                "summary": summary
            }

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

            checkpoint_info = {
                "projectPath": project_path,
                "absolutePath": str(file_path.resolve()),
                "tag": tag,
                "file": file_path.stem,
                "messageCount": len(history),
                "authType": auth_type,
                "lastUpdated": last_updated
            }

            checkpoints.append(checkpoint_info)

        except Exception:
            continue

    return checkpoints

def main():
    parser = argparse.ArgumentParser(description="List Gemini CLI sessions and checkpoints")
    parser.add_argument("--all", action="store_true", help="List sessions for all registered projects. Otherwise, only lists for the current project.")
    parser.add_argument("--json", action="store_true", help="Output in JSON format.")
    args = parser.parse_args()

    projects = get_projects()
    home_dir = Path.home()
    cwd = str(Path.cwd().resolve())

    target_projects = {}

    if args.all:
        target_projects = projects
    else:
        for path, short_id in projects.items():
            if os.path.normpath(path) == os.path.normpath(cwd):
                target_projects[path] = short_id
                break

        if not target_projects:
            if args.json:
                print(json.dumps({
                    "sessions": [],
                    "checkpoints": [],
                    "error": "No previous sessions found for this project."
                }, indent=2))
            else:
                print("No previous sessions found for this project.")
            return

    all_sessions = []
    all_checkpoints = []

    for project_path, short_id in target_projects.items():
        project_tmp_dir = home_dir / ".gemini" / "tmp" / short_id
        all_sessions.extend(get_sessions(project_tmp_dir, project_path))
        all_checkpoints.extend(get_checkpoints(project_tmp_dir, project_path))

    all_sessions.sort(key=lambda x: parse_isoformat(x["lastUpdated"]), reverse=True)
    all_checkpoints.sort(key=lambda x: parse_isoformat(x["lastUpdated"]), reverse=True)

    if args.json:
        output = {
            "sessions": all_sessions,
            "checkpoints": all_checkpoints
        }
        print(json.dumps(output, indent=2))
    else:
        # Replicate CLI output
        # CLI orders sessions chronologically ascending when numbering them.
        # So we'll sort the final display sessions by startTime ascending for the list.
        display_sessions = sorted(all_sessions, key=lambda x: parse_isoformat(x["startTime"]))
        display_checkpoints = sorted(all_checkpoints, key=lambda x: parse_isoformat(x["lastUpdated"]), reverse=True)

        if len(display_sessions) > 0:
            print(f"\nAvailable sessions for this project ({len(display_sessions)}):")
            for session in display_sessions:
                time_str = format_relative_time(session["lastUpdated"])
                title = session["displayName"]
                if len(title) > 100:
                    title = title[:97] + "..."

                print(f"  {session['index']}. {title} ({time_str}) [{session['id']}]")
                print(f"     Path: {session['absolutePath']}\n")
        else:
            print("No previous sessions found for this project.")

        if len(display_checkpoints) > 0:
            print(f"\nAvailable checkpoints for this project ({len(display_checkpoints)}):")
            for i, ckpt in enumerate(display_checkpoints):
                time_str = format_relative_time(ckpt["lastUpdated"])
                title = ckpt["tag"]
                if len(title) > 100:
                    title = title[:97] + "..."

                print(f"  {i + 1}. {title} ({time_str})")
                print(f"     Path: {ckpt['absolutePath']}\n")

if __name__ == "__main__":
    main()
