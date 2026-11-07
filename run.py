#!/usr/bin/env python3
"""Entry point for Quality Forge orchestrator (cross-platform).

Usage:
  python3 run.py
  python3 run.py --loop --max 500
  python3 run.py --validate
  python3 run.py --score
"""
from forge.orchestrator import main

if __name__ == "__main__":
    raise SystemExit(main())
