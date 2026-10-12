"""Frozen worker/tracker children must exit before creating manager Events."""

import subprocess
import sys


def test_frozen_child_role_handled_before_sidecar_manager():
    script = (
        "import multiprocessing as mp, sys; "
        "sys.frozen = True; "
        "mp.freeze_support = lambda: sys.exit(42); "
        "import sidecar.server"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 42, result.stderr
