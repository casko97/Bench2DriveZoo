import os
import signal
import subprocess
import sys
import time
from pathlib import Path


SUPERVISOR = Path(__file__).resolve().parents[1] / 'scripts' / 'supervise_evaluator.py'


def wait_for_file(path):
    deadline = time.monotonic() + 10
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert path.exists()


def test_interrupt_forces_stalled_evaluator_and_child(tmp_path):
    child_pid_file = tmp_path / 'child.pid'
    child = "import os,signal,time; signal.signal(signal.SIGINT, signal.SIG_IGN); open(os.environ['PID_FILE'],'w').write(str(os.getpid())); time.sleep(60)"
    evaluator = "import os,signal,subprocess,sys,time; signal.signal(signal.SIGINT, signal.SIG_IGN); subprocess.Popen([sys.executable,'-c',sys.argv[1]], start_new_session=True); time.sleep(60)"
    env = dict(os.environ, PID_FILE=str(child_pid_file))
    process = subprocess.Popen([sys.executable, str(SUPERVISOR), sys.executable, '-c', evaluator, child],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_for_file(child_pid_file)
        child_pid = int(child_pid_file.read_text())
        time.sleep(0.5)  # Allow the supervisor to observe the child process.
        process.send_signal(signal.SIGINT)
        time.sleep(0.5)
        assert process.poll() is None
        process.send_signal(signal.SIGINT)
        output, _ = process.communicate(timeout=10)
        assert process.returncode == 130
        assert 'Forcing shutdown' in output
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            stat = Path('/proc/{}/stat'.format(child_pid))
            if not stat.exists() or stat.read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                break
            time.sleep(0.05)
        else:
            raise AssertionError('Evaluator child was left running')
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_success_exit_is_preserved():
    result = subprocess.run([sys.executable, str(SUPERVISOR), sys.executable, '-c', 'pass'], timeout=10)
    assert result.returncode == 0
