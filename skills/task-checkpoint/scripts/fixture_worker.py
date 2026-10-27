#!/usr/bin/env python3
"""Deterministic demonstration worker; no model, network, tools, or arbitrary command."""
import os
from pathlib import Path
import sys

if __name__ == '__main__':
    value = sys.argv[1]
    if value not in ('42', 'wrong'):
        raise SystemExit('Fixture accepts only the documented synthetic results')
    Path(os.environ['CHECKPOINT_RESULT']).write_text(value, encoding='utf-8')
