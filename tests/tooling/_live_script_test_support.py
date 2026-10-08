from __future__ import annotations

import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


requires_windows = pytest.mark.skipif(
    os.name != "nt", reason="requires Windows PowerShell"
)
