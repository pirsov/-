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
    "status": "idle",  # idle|running|done|error|waiting_human|looping
    "started_at": None,
    "ended_at": None,
    "exit_code": None,
    "pid": None,
    "log_path": None,
    "report": {},
    "mode": None,  # week|loop_24h
    "waiting_reason": None,
    "waiting_detail": None,
    "loop_cycle": 0,
    "loop_max": 0,
    "stop_requested": False,
}

_stop_event = threading.Event()
_loop_thread: Optional[threading.Thread] = None


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
        # don't clobber waiting_human report with empty parse during wait
        if st.get("status") not in {"waiting_human"}:
            st["report"] = _parse_report(text) if text.strip() else st.get("report") or {}
    st["log_tail"] = log_tail
    st["stop_requested"] = _stop_event.is_set()
    return st


def set_waiting_human(*, reason: str = "hitl", detail: Optional[Dict[str, Any]] = None) -> None:
    """Pause autonomous work until /api/answer — no CPU burn."""
    with _lock:
        _state.update(
            {
                "status": "waiting_human",
                "waiting_reason": reason,
                "waiting_detail": detail or {},
                "ended_at": None,
            }
        )


def clear_waiting_human() -> None:
    with _lock:
        if _state.get("status") == "waiting_human":
            # return to idle unless a loop thread is still marked looping
            mode = _state.get("mode")
            _state["waiting_reason"] = None
            _state["waiting_detail"] = None
            if mode == "loop_24h" and not _stop_event.is_set():
                _state["status"] = "looping"
            else:
                _state["status"] = "idle"
                _state["mode"] = None


def stop_24h(*, join_timeout: float = 5.0) -> Dict[str, Any]:
    """Signal stop and join the 24h thread so log files close (Windows temp cleanup)."""
    global _loop_thread
    _stop_event.set()
    with _lock:
        _state["stop_requested"] = True
        pid = _state.get("pid")
    if pid:
        try:
            import os as _os
            import signal

            _os.kill(int(pid), signal.SIGTERM)
        except Exception:
            pass
    # A16/Windows: wait until loop exits so loop24-*.log handle is released
    t = _loop_thread
    if t is not None and t.is_alive():
        t.join(timeout=max(0.5, float(join_timeout)))
    with _lock:
        if _state.get("status") in {"looping", "running", "waiting_human"}:
            _state["status"] = "idle"
            _state["mode"] = None
            _state["ended_at"] = datetime.now(timezone.utc).isoformat()
        if t is not None and not t.is_alive():
            _loop_thread = None
    return {"ok": True, **status()}


def start_24h(
    root: Optional[Path] = None,
    *,
    sleep: float = 30.0,
    max_cycles: int = 48,
    week_max_steps: int = 5,
) -> Dict[str, Any]:
    """
    Autonomous loop: plan_next → if waiting_human park; else run short --week batch.
    Does not spin CPU while waiting_human.
    """
    root = root or ROOT_DEFAULT
    global _loop_thread
    # Copy under lock, then call status() OUTSIDE — Lock is not re-entrant (UI hang).
    with _lock:
        cur = dict(_state)
    if cur.get("status") in {"running", "looping"}:
        return {"ok": False, "error": "already running", **status()}
    if cur.get("status") == "waiting_human" and cur.get("mode") == "loop_24h":
        return {"ok": False, "error": "already waiting_human in 24h mode", **status()}

    _stop_event.clear()
    run_dir = _run_dir(root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = run_dir / f"loop24-{stamp}.log"

    def _park_waiting(logf, *, reason: str = "waiting_human") -> None:
        """Block until human answers / stop — does NOT advance cycle."""
        park_s = max(5.0, float(sleep) or 5.0)
        logf.write(f"{reason} - parked (cycle paused, wake every {park_s:.0f}s)\n")
        logf.flush()
        # slice sleeps so stop_event + answer are responsive
        slice_s = 1.0
        slices = max(1, int(park_s / slice_s))
        while not _stop_event.is_set():
            if status().get("status") != "waiting_human":
                return
            for _ in range(slices):
                if _stop_event.is_set():
                    return
                if status().get("status") != "waiting_human":
                    return
                time.sleep(slice_s)

    def _loop() -> None:
        cycle = 0
        with log_path.open("w", encoding="utf-8") as logf:
            logf.write(f"# 24h loop start {stamp} max_cycles={max_cycles}\n")
            logf.flush()
            while not _stop_event.is_set() and cycle < max_cycles:
                try:
                    from . import planner as planner_hub

                    # Never overwrite waiting_human → looping (that burned 48 cycles in ~1s)
                    st = status()
                    if st.get("status") == "waiting_human":
                        _park_waiting(logf)
                        continue

                    with _lock:
                        if _state.get("status") != "waiting_human":
                            _state.update(
                                {
                                    "status": "looping",
                                    "mode": "loop_24h",
                                    "loop_cycle": cycle,
                                    "loop_max": max_cycles,
                                    "log_path": str(log_path),
                                    "started_at": _state.get("started_at")
                                    or datetime.now(timezone.utc).isoformat(),
                                }
                            )

                    plan = planner_hub.plan_next(root)
                    logf.write(
                        f"plan_next action={plan.get('action')} "
                        f"(work_cycle={cycle}/{max_cycles})\n"
                    )
                    logf.flush()
                    if plan.get("action") in {"ask_hitl", "verify_plugin"}:
                        set_waiting_human(
                            reason=str(plan.get("action")),
                            detail={k: plan.get(k) for k in ("plugin", "hint") if plan.get(k)},
                        )
                        # Park here without incrementing cycle — human answer resumes same budget
                        _park_waiting(logf, reason=f"-> waiting_human ({plan.get('action')})")
                        continue

                    # Count only productive work cycles (week bursts)
                    cycle += 1
                    with _lock:
                        if _state.get("status") == "waiting_human":
                            cycle = max(0, cycle - 1)
                            continue
                        _state["loop_cycle"] = cycle
                    logf.write(f"\n## cycle {cycle}/{max_cycles}\n")
                    logf.flush()

                    # allow_from_loop: status is "looping" here; without it start_week
                    # deadlocks (status() under Lock) or returns "already running".
                    burst = start_week(
                        root,
                        sleep=0.0,
                        hitl="y",
                        max_steps=week_max_steps,
                        allow_from_loop=True,
                    )
                    logf.write(
                        "week burst: "
                        + json.dumps(
                            {
                                k: burst.get(k)
                                for k in ("ok", "status", "pid", "error")
                                if burst.get(k) is not None
                            }
                        )
                        + "\n"
                    )
                    logf.flush()
                    if not burst.get("ok"):
                        logf.write(f"week burst blocked: {burst.get('error')}\n")
                        logf.flush()
                        time.sleep(min(2.0, float(sleep) or 2.0))
                        continue
                    # wait until week finishes or stop
                    while status().get("status") == "running" and not _stop_event.is_set():
                        time.sleep(1.0)
                    # pacing between cycles
                    pace = max(1, int(float(sleep) or 0) or 1)
                    for _ in range(pace):
                        if _stop_event.is_set():
                            break
                        if status().get("status") == "waiting_human":
                            break
                        time.sleep(1)
                except Exception as e:
                    logf.write(f"loop error: {type(e).__name__}: {e}\n")
                    logf.flush()
                    time.sleep(min(5.0, float(sleep) or 5.0))

            with _lock:
                _state.update(
                    {
                        "status": "done" if not _stop_event.is_set() else "idle",
                        "mode": None,
                        "ended_at": datetime.now(timezone.utc).isoformat(),
                        "pid": None,
                    }
                )
            logf.write("\n# 24h loop end\n")
            logf.flush()

    with _lock:
        _state.update(
            {
                "status": "looping",
                "mode": "loop_24h",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ended_at": None,
                "exit_code": None,
                "log_path": str(log_path),
                "loop_cycle": 0,
                "loop_max": max_cycles,
                "stop_requested": False,
                "report": {"phase": "loop_24h"},
            }
        )
    _loop_thread = threading.Thread(target=_loop, name="forge-24h", daemon=True)
    _loop_thread.start()
    time.sleep(0.1)
    return {"ok": True, **status()}


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
    allow_from_loop: bool = False,
) -> Dict[str, Any]:
    root = root or ROOT_DEFAULT
    # Never call status() while holding _lock — non-reentrant Lock deadlocks the UI thread.
    with _lock:
        cur = dict(_state)
    if cur.get("status") == "running":
        return {"ok": False, "error": "already running", **status()}
    if cur.get("status") == "looping" and not allow_from_loop:
        return {"ok": False, "error": "already running", **status()}
    # week start blocked while 24h is parked for HITL (unless internal loop resume)
    if (
        cur.get("status") == "waiting_human"
        and cur.get("mode") == "loop_24h"
        and not allow_from_loop
    ):
        return {"ok": False, "error": "waiting_human — answer via /api/answer first", **status()}

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
                # Hand control back to 24h loop when this was an inner burst
                if _state.get("mode") == "loop_24h" and not _stop_event.is_set():
                    next_status = "looping"
                else:
                    next_status = "done" if code == 0 else "error"
                _state.update(
                    {
                        "status": next_status,
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
            if code == 0 or report.get("quality"):
                try:
                    from . import progress_hub

                    progress_hub.mark(root, run_done=True)
                except Exception:
                    pass

    with _lock:
        # Preserve mode=loop_24h when burst comes from the autonomous loop
        prev_mode = _state.get("mode")
        _state.update(
            {
                "status": "running",
                "mode": prev_mode if allow_from_loop and prev_mode == "loop_24h" else "week",
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
