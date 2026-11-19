"""Feedback closed-loop evaluator entry point."""
import runpy
import sys
from pathlib import Path

sys.argv.insert(1, "--feedback-pipeline")
runpy.run_path(str(Path(__file__).with_name("closed_loop_evaluator.py")), run_name="__main__")
