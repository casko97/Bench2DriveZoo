"""Verify the two public entry points select shared behavior without conflating modes."""

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('script, expected', [
    ('run_evaluator_with_progress.py', ['wrapper', 'evaluator.py', '--routes=test']),
    ('run_feedback_evaluator.py', ['wrapper', '--feedback-pipeline', 'evaluator.py', '--routes=test']),
])
def test_evaluator_entrypoint_selects_mode(monkeypatch, script, expected):
    import runpy
    observed = []
    monkeypatch.setattr(sys, 'argv', ['wrapper', 'evaluator.py', '--routes=test'])
    monkeypatch.setattr(runpy, 'run_path', lambda path, run_name: observed.append((path, run_name, list(sys.argv))))
    path = ROOT / 'scripts' / script
    exec(compile(path.read_text(), str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
    assert observed == [(str(ROOT / 'scripts' / 'closed_loop_evaluator.py'), '__main__', expected)]


@pytest.mark.parametrize('script', ['run_closed_loop_vad_v004.sh', 'run_feedback_closed_loop_vad_v004.sh'])
def test_launcher_preserves_argument_validation(script):
    result = subprocess.run([str(ROOT / 'scripts' / script), '--not-an-option'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 2
    assert 'Unknown argument: --not-an-option' in result.stderr
