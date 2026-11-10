#!/usr/bin/env python3
"""Entry point for Quality Forge orchestrator (cross-platform).

Usage:
  python3 run.py
  python3 run.py --loop --max 500
  python3 run.py --validate
  python3 run.py --score
"""
import sys
import io

# Windows consoles often default to cp1251/cp1252 (charmap). Force UTF-8 so
# status lines with arrows/approx do not raise UnicodeEncodeError.
if sys.platform.startswith("win"):
    try:
        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
    except Exception:
        # Keep original streams if reassignment fails (errors='replace' already preferred).
        pass

# A21.0: line-buffer stdout/stderr so UI /api/logs sees progress during long Ollama gens
# (Windows often block-buffers even with python -u / PYTHONUNBUFFERED).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(line_buffering=True)
    except Exception:
        pass

from forge.orchestrator import main

if __name__ == "__main__":
    raise SystemExit(main())
