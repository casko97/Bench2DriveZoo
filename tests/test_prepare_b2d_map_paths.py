from pathlib import Path
import pickle
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'mmcv' / 'datasets' / 'prepare_B2D_mini.py'

# The map path tests only need empty maps. Stub the heavy optional dependencies
# so they can run in a plain Python environment, while executing the real CLI.
RUNNER = r'''
import pickle, runpy, sys, types
class Matrix:
    def __setitem__(self, key, value): pass
class Archive:
    def __init__(self, path): self.path = path
    def __enter__(self):
        with open(self.path, 'rb') as f: self.data = pickle.load(f)
        return self
    def __exit__(self, *args): pass
    def __getitem__(self, key): return self.data[key]
numpy = types.ModuleType('numpy')
numpy.array = lambda value: Matrix()
numpy.eye = lambda size: Matrix()
numpy.load = lambda path, allow_pickle: Archive(path)
sys.modules['numpy'] = numpy
quaternion = types.ModuleType('pyquaternion')
quaternion.Quaternion = object
sys.modules['pyquaternion'] = quaternion
progress = types.ModuleType('tqdm')
def tqdm(items, **kwargs): return items
tqdm.write = print
progress.tqdm = tqdm
sys.modules['tqdm'] = progress
vis = types.ModuleType('vis_utils')
for name in ('calculate_cube_vertices', 'calculate_occlusion_stats', 'edges', 'DIS_CAR_SAVE'):
    setattr(vis, name, None)
sys.modules['vis_utils'] = vis
sys.modules['cv2'] = types.ModuleType('cv2')
script = sys.argv.pop(1)
runpy.run_path(script, run_name='__main__')
'''


class MapPathArgumentsTest(unittest.TestCase):
    def run_script(self, cwd, *args):
        return subprocess.run(
            [sys.executable, '-c', RUNNER, str(SCRIPT), *map(str, args)],
            cwd=cwd, text=True, capture_output=True,
        )

    def test_custom_paths_create_map_info_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            maps = root / 'input maps'
            maps.mkdir()
            with (maps / 'Town11_HD_map.npz').open('wb') as f:
                pickle.dump({'arr': {}}, f)
            output = root / 'custom output' / 'infos'

            result = self.run_script(root, '--maps-only', '--map-root', maps, '--out-dir', output)

            self.assertEqual(result.returncode, 0, result.stderr)
            with (output / 'b2d_map_infos.pkl').open('rb') as f:
                self.assertEqual(list(pickle.load(f)), ['Town11'])
            self.assertTrue((output / '.b2d_map_infos_cache' / 'Town11_HD_map.npz.pkl').is_file())
            self.assertFalse((root / 'data' / 'infos').exists())

    def test_default_paths_and_missing_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / 'mmcv' / 'datasets'
            cwd.mkdir(parents=True)
            maps = root / 'data' / 'bench2drive' / 'maps'
            maps.mkdir(parents=True)
            with (maps / 'Town01_HD_map.npz').open('wb') as f:
                pickle.dump({'arr': {}}, f)

            result = self.run_script(cwd, '--maps-only')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / 'data' / 'infos' / 'b2d_map_infos.pkl').is_file())

            result = self.run_script(cwd, '--maps-only', '--map-root', root / 'missing')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('FileNotFoundError', result.stderr)


if __name__ == '__main__':
    unittest.main()
