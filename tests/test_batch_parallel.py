import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class BatchParallelTests(unittest.TestCase):
    def test_port_reservations_are_distinct_and_released(self):
        script = ROOT / 'scripts/reserve_batch_ports.sh'
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, BATCH_PORT_LOCK_DIR=tmp, SLURM_JOB_ID='876543')
            command = 'source "$1"; printf "PORTS %s %s\\n" "$PORT" "$TM_PORT"; read -r _'
            processes = []
            try:
                ports = []
                for _ in range(2):
                    process = subprocess.Popen(['bash', '-c', command, 'probe', str(script)],
                                               env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, text=True)
                    processes.append(process)
                    first = process.stdout.readline()
                    second = process.stdout.readline()
                    self.assertIn('Reserved node-local', first)
                    self.assertTrue(second.startswith('PORTS '), second)
                    rpc, tm = map(int, second.split()[1:])
                    self.assertEqual(tm, rpc + 4)
                    ports.append(rpc)
                self.assertNotEqual(*ports)
            finally:
                for process in processes:
                    if process.stdin:
                        process.stdin.close()
                    process.wait(timeout=10)
                    if process.stdout:
                        process.stdout.close()
                    if process.stderr:
                        process.stderr.close()

    def test_submission_defaults_to_scheduler_control_with_optional_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'scripts').mkdir()
            (root / 'bin').mkdir()
            for name in ('submit_closedloop_vad_batches.sh', 'select_closed_loop_batch.py'):
                shutil.copy(ROOT / 'scripts' / name, root / 'scripts' / name)
            sbatch = root / 'bin/sbatch'
            sbatch.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$BATCH_QUEUE_DIR/args"\n')
            sbatch.chmod(0o755)
            routes = root / 'routes.xml'
            routes.write_text('<routes>' + ''.join('<route id="%s"/>' % i for i in range(12)) + '</routes>')
            env = dict(os.environ, PATH=str(root / 'bin') + os.pathsep + os.environ['PATH'], BATCH_ROUTES=str(routes))
            env.pop('MAX_CONCURRENT', None)
            env.pop('BATCH_GROUP_BY_TOWN', None)
            for cap, expected in ((None, '--array=0-2'), ('2', '--array=0-2%2')):
                if cap is None:
                    env.pop('MAX_CONCURRENT', None)
                else:
                    env['MAX_CONCURRENT'] = cap
                result = subprocess.run(['bash', 'scripts/submit_closedloop_vad_batches.sh'], cwd=str(root),
                                        env=env, check=True, capture_output=True, text=True)
                queue = pathlib.Path(result.stdout.splitlines()[0].split(': ', 1)[1])
                self.assertIn(expected, (queue / 'args').read_text().splitlines())


if __name__ == '__main__':
    unittest.main()
