import json
import tempfile
import threading
import unittest
from pathlib import Path

from team_code.artifact_writer import ArtifactWriter, write_artifacts


class ArtifactWriterTests(unittest.TestCase):
    def test_close_flushes_in_order_and_backpressure_is_bounded(self):
        started, release, submitted = threading.Event(), threading.Event(), threading.Event()
        written = []

        def write(item):
            if item == 0:
                started.set()
                self.assertTrue(release.wait(5))
            written.append(item)

        writer = ArtifactWriter(write, max_pending=1)
        try:
            writer.submit(0)
            self.assertTrue(started.wait(5))
            writer.submit(1)
            def submit_last():
                writer.submit(2)
                submitted.set()
            producer = threading.Thread(target=submit_last)
            producer.start()
            self.assertFalse(submitted.wait(0.1))
            release.set()
            producer.join(5)
            self.assertTrue(submitted.is_set())
            writer.close()
            self.assertEqual(written, [0, 1, 2])
            with self.assertRaises(RuntimeError):
                writer.submit(3)
        finally:
            release.set()
            writer.close()

    def test_errors_propagate_and_shutdown_does_not_hang(self):
        attempted, release = threading.Event(), threading.Event()
        def fail(item):
            attempted.set()
            release.wait(5)
            raise OSError('disk full')
        writer = ArtifactWriter(fail, max_pending=1)
        writer.submit('frame')
        self.assertTrue(attempted.wait(5))
        release.set()
        with self.assertRaisesRegex(RuntimeError, 'Background artifact writing failed') as caught:
            writer.close()
        self.assertIsInstance(caught.exception.__cause__, OSError)
        with self.assertRaises(RuntimeError):
            writer.check()

    def test_output_matches_original_write(self):
        import cv2
        import numpy as np
        from PIL import Image

        rng = np.random.RandomState(4)
        images = {'rgb_front': rng.randint(0, 256, (80, 128, 3), dtype=np.uint8),
                  'bev': rng.randint(0, 256, (32, 32, 3), dtype=np.uint8)}
        metadata = {'steer': 0.2, 'plan': [[1, 2]]}
        metrics = {1: {'location': [1, 2, 3]}}
        for jpeg in (False, True):
            with self.subTest(jpeg=jpeg), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                for name in ('rgb_front', 'bev', 'meta'):
                    (root / name).mkdir()
                writer = ArtifactWriter(lambda item: write_artifacts(root, jpeg, item))
                writer.submit((3, images, metadata, metrics))
                writer.close()
                expected = images['rgb_front']
                if jpeg:
                    _, encoded = cv2.imencode('.jpg', expected, [int(cv2.IMWRITE_JPEG_QUALITY), 20])
                    expected = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                np.testing.assert_array_equal(np.asarray(Image.open(root / 'rgb_front' / '0003.png')), expected)
                np.testing.assert_array_equal(np.asarray(Image.open(root / 'bev' / '0003.png')), images['bev'])
                self.assertEqual(json.loads((root / 'meta' / '0003.json').read_text()), metadata)
                self.assertEqual(json.loads((root / 'metric_info.json').read_text()), {'1': metrics[1]})


if __name__ == '__main__':
    unittest.main()
