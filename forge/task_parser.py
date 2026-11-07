"""Parse PROJECT_TZ task lines into structured Task objects."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class WriteMode(str, Enum):
    CREATE = "create"  # write full file (overwrite ok for rewrite tasks)
    APPEND = "append"  # always append if file exists
    REWRITE = "rewrite"  # full replace
    DOCS = "docs"  # markdown section append/write
    REVIEW = "review"  # may produce report without code
    UNKNOWN = "unknown"


@dataclass
class Task:
    raw: str
    task_id: str
    owner: str
    mode: WriteMode
    target_path: Optional[str] = None
    section: Optional[str] = None
    requires_file: bool = False
    description: str = ""


_TASK_RE = re.compile(
    r"^\s*- \[ \] (P\d+(?:\.\d+)*)\s*\|\s*(.+?)\s*\|\s*@(\w+)(?:\s*\|\s*→\s*(.+))?\s*$"
)


def detect_mode(description: str) -> WriteMode:
    d = description.lower()
    if re.search(r"\bappend\b", d):
        return WriteMode.APPEND
    if re.search(r"\brewrite\b|\bfrom scratch\b|\bwith exactly\b", d):
        return WriteMode.REWRITE
    # "Fix HIGH/CRIT..." and integrator passes rewrite existing files
    if re.search(r"\bfix\b|\bverify\b|\bmismatch|\bedit\b|\bpatch\b", d):
        return WriteMode.REWRITE
    if re.search(r"\bcreate\b|\bwrite\b", d):
        return WriteMode.CREATE
    if re.search(r"\breview\b|\bqa\b|\breport\b|\bscore\b", d):
        return WriteMode.REVIEW
    if ".md" in d:
        return WriteMode.DOCS
    return WriteMode.UNKNOWN


def parse_task_line(line: str) -> Optional[Task]:
    m = _TASK_RE.match(line.rstrip())
    if not m:
        # Fallback: looser match used by legacy TZ lines
        m2 = re.match(
            r"^\s*- \[ \] (P\d+(?:\.\d+)*)\s*\|(.+?)\|\s*@(\w+)(.*)$",
            line,
        )
        if not m2:
            return None
        task_id, desc, owner, rest = m2.group(1), m2.group(2).strip(), m2.group(3), m2.group(4)
        target = section = None
        am = re.search(r"→\s*([^\s|#]+)(?:#([^\s|]+))?", rest)
        if am:
            target, section = am.group(1), am.group(2)
        mode = detect_mode(desc)
        return Task(
            raw=line,
            task_id=task_id,
            owner=owner,
            mode=mode,
            target_path=target,
            section=section,
            requires_file=bool(target) or mode in {WriteMode.CREATE, WriteMode.APPEND, WriteMode.REWRITE},
            description=desc,
        )

    task_id, desc, owner, arrow = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
    target = section = None
    if arrow:
        arrow = arrow.strip()
        if "#" in arrow:
            target, section = arrow.split("#", 1)
            target = target.strip()
            section = section.strip()
        else:
            target = arrow.strip()
            # strip trailing parenthetical notes
            target = re.split(r"\s+\(", target, 1)[0].strip()

    mode = detect_mode(desc)
    if section:
        mode = WriteMode.APPEND if mode == WriteMode.UNKNOWN else mode
        if mode == WriteMode.CREATE:
            mode = WriteMode.APPEND

    # Require <FILE> when a concrete path is given, or CREATE/APPEND (must produce a file).
    # REWRITE/Fix without → path may emit 0..N files (e.g. "no HIGH bugs" = NOTE only).
    requires = bool(target) or mode in {
        WriteMode.CREATE,
        WriteMode.APPEND,
        WriteMode.DOCS,
    }
    # Explicit no-op / note-only tasks (even with → path for reference)
    if re.search(r"no <file>|note only|no code changes|already match", desc, re.I):
        requires = False
    return Task(
        raw=line,
        task_id=task_id,
        owner=owner,
        mode=mode,
        target_path=target,
        section=section,
        requires_file=requires,
        description=desc,
    )


def find_pending_tasks(tz_text: str) -> List[Task]:
    tasks: List[Task] = []
    for line in tz_text.splitlines():
        if not re.match(r"^\s*- \[ \] ", line):
            continue
        t = parse_task_line(line)
        if t:
            tasks.append(t)
    return tasks
