"""Skip, rather than fail, the tests that need the self-hosted model libraries when they are not installed.

The lightweight environment (requirements/edgebench.txt + requirements/analysis.txt) runs every test that needs no
model library. Install requirements/edgebench-local.txt (macOS arm64) or requirements/edgebench-cuda.txt (Linux + CUDA)
to run the full suite.
"""
import importlib.util

import pytest

MODEL_LIBRARIES = ("torch", "laya", "transformers", "sentence_transformers", "outlines", "mlx")
MISSING = {name for name in MODEL_LIBRARIES if importlib.util.find_spec(name) is None}

# These modules import torch at module level, so they cannot even be collected without it.
collect_ignore = ["test_eb_p2e_cuda.py", "test_eb_p2g_regressions.py"] if "torch" in MISSING else []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    exc = call.excinfo
    if exc is not None and exc.errisinstance(ModuleNotFoundError) and exc.value.name in MISSING:
        report.outcome = "skipped"
        report.longrepr = (str(item.path), item.location[1], f"requires the model library '{exc.value.name}'")
