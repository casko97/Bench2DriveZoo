"""Standard closed-loop evaluator entry point."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("closed_loop_evaluator.py")), run_name="__main__")
