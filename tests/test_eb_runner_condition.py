"""The runner must hand the run's condition to build_interpreter (the retrained classifier picks its head from it)."""
from pathlib import Path

import src.edgebench.runner as runner


def test_run_benchmark_passes_condition_to_build_interpreter(monkeypatch, tmp_path: Path):
    seen = {}

    class Stop(Exception):
        pass

    def fake_build(name, manifest=None, api_key=None, base_url=None, condition=None):
        seen["condition"] = condition
        raise Stop

    monkeypatch.setattr(runner, "build_interpreter", fake_build)
    monkeypatch.setattr(runner, "load_manifest", lambda *a, **k: {})
    cases = tmp_path / "test.jsonl"
    cases.write_text("")
    try:
        runner.run_benchmark(cases_path=str(cases), rq="RQ4", condition="churn25", model_names=["X"],
                             out_dir=str(tmp_path / "out"), allow_dirty=True)
    except Stop:
        pass
    assert seen["condition"] == "churn25"
