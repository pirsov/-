"""Background --week runner for the control UI (log + report + code snapshot)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DEFAULT = Path(__file__).resolve().parents[1]

_lock = threading.Lock()
_state: Dict[str, Any] = {
    "status": "idle",  # idle|running|done|error
    "started_at": None,
    "ended_at": None,
    "exit_code": None,
    "pid": None,
    "log_path": None,
    "report": {},
}


def _run_dir(root: Path) -> Path:
    d = root / ".forge" / "ui_run"
    d.mkdir(parents=True, exist_ok=True)
    return d


def status() -> Dict[str, Any]:
    with _lock:
        st = dict(_state)
    log_path = st.get("log_path")
    log_tail = ""
    if log_path and Path(log_path).exists():
        text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        log_tail = text[-12000:]
        st["report"] = _parse_report(text)
    st["log_tail"] = log_tail
    return st


def full_log(root: Optional[Path] = None) -> str:
    root = root or ROOT_DEFAULT
    with _lock:
        p = _state.get("log_path")
    if not p:
        p = str(_run_dir(root) / "latest.log")
    path = Path(p)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def list_code_files(root: Optional[Path] = None, *, limit: int = 40) -> List[Dict[str, Any]]:
    root = root or ROOT_DEFAULT
    out: List[Dict[str, Any]] = []
    src = root / "src"
    if not src.exists():
        return out
    for p in sorted(src.rglob("*.luau")):
        rel = p.relative_to(root).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        out.append(
            {
                "path": rel,
                "chars": len(text),
                "preview": text[:400],
            }
        )
        if len(out) >= limit:
            break
    return out


def read_code_file(rel: str, root: Optional[Path] = None, *, max_chars: int = 40000) -> Dict[str, Any]:
    root = root or ROOT_DEFAULT
    # prevent path escape
    rel = rel.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("bad path")
    path = (root / rel).resolve()
    if not str(path).startswith(str(root.resolve())):
        raise ValueError("path outside root")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(rel)
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"path": rel, "chars": len(text), "content": text[:max_chars]}


def start_week(
    root: Optional[Path] = None,
    *,
    sleep: float = 0.0,
    hitl: str = "y",
    max_steps: Optional[int] = None,
) -> Dict[str, Any]:
    root = root or ROOT_DEFAULT
    with _lock:
        if _state.get("status") == "running":
            return {"ok": False, "error": "already running", **status()}

    run_dir = _run_dir(root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = run_dir / f"{stamp}.log"
    (run_dir / "latest.log").unlink(missing_ok=True)

    cmd = [
        sys.executable,
        "-u",
        str(root / "run.py"),
        "--week",
        "--sleep",
        str(sleep),
        "--hitl",
        hitl,
        "--root",
        str(root),
    ]
    if max_steps is not None:
        cmd.extend(["--max", str(max_steps)])

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("FORGE_BACKEND", "ollama")
    env["OLLAMA_NUM_PARALLEL"] = env.get("OLLAMA_NUM_PARALLEL") or "1"

    def _worker() -> None:
        with log_path.open("w", encoding="utf-8") as logf:
            logf.write(f"# start {stamp}\n# cmd {' '.join(cmd)}\n\n")
            logf.flush()
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env=env,
                    text=True,
                    bufsize=1,
                )
            except Exception as e:
                with _lock:
                    _state.update(
                        {
                            "status": "error",
                            "ended_at": datetime.now(timezone.utc).isoformat(),
                            "exit_code": -1,
                            "report": {"error": str(e)},
                        }
                    )
                logf.write(f"FAILED TO SPAWN: {e}\n")
                return

            with _lock:
                _state["pid"] = proc.pid

            assert proc.stdout is not None
            for line in proc.stdout:
                logf.write(line)
                logf.flush()
                # mirror latest
                try:
                    (run_dir / "latest.log").write_text(
                        log_path.read_text(encoding="utf-8", errors="replace"),
                        encoding="utf-8",
                    )
                except OSError:
                    pass

            code = proc.wait()
            text = log_path.read_text(encoding="utf-8", errors="replace")
            report = _parse_report(text)
            report["files"] = [f["path"] for f in list_code_files(root)]
            (run_dir / "latest_report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            with _lock:
                _state.update(
                    {
                        "status": "done" if code == 0 else "error",
                        "ended_at": datetime.now(timezone.utc).isoformat(),
                        "exit_code": code,
                        "pid": None,
                        "report": report,
                    }
                )
            try:
                (run_dir / "latest.log").write_text(text, encoding="utf-8")
            except OSError:
                pass

    with _lock:
        _state.update(
            {
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ended_at": None,
                "exit_code": None,
                "pid": None,
                "log_path": str(log_path),
                "report": {"phase": "starting"},
            }
        )

    t = threading.Thread(target=_worker, name="forge-week-ui", daemon=True)
    t.start()
    # tiny wait so pid may appear
    time.sleep(0.15)
    return {"ok": True, **status()}


def _parse_report(log: str) -> Dict[str, Any]:
    done = re.findall(r"(?m)^\[([A-Z]?\d+)\] -> @(\w+).*", log)
    done_ids = []
    for m in re.finditer(r"(?m)^\s*DONE:\s*([A-Z]?\d+)\b", log):
        done_ids.append(m.group(1))
    # also "DONE: T1 -" style from note
    for m in re.finditer(r"(?m)^\s*DONE:\s*([A-Z]?\d+)\s*-", log):
        if m.group(1) not in done_ids:
            done_ids.append(m.group(1))
    wrote = re.findall(r"(?m)^\s*wrote (src/\S+|docs/\S+)", log)
    fails = re.findall(r"(?m)VALIDATOR FAIL[^:\n]*:\s*(.+)$", log)
    quality = None
    mq = re.search(r"Final quality score:\s*(\d+)/100", log)
    if mq:
        quality = int(mq.group(1))
    else:
        mq2 = re.findall(r"quality=(\d+)", log)
        if mq2:
            quality = int(mq2[-1])
    hitl = "HITL:" in log or "needs YOU" in log
    return {
        "started_tasks": [{"id": a, "owner": b} for a, b in done],
        "done_notes": done_ids,
        "wrote_files": wrote,
        "validator_fails": fails[-12:],
        "quality": quality,
        "hitl_seen": hitl,
        "lines": log.count("\n") + 1,
        "chars": len(log),
    }
