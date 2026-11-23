"""Ordered, bounded background writing for evaluation artifacts."""
import queue
import threading
import json


def write_artifacts(path, jpeg_roundtrip, payload):
    import cv2
    from PIL import Image

    frame, images, metadata, metric_info = payload
    for view, image in images.items():
        if view != 'bev' and jpeg_roundtrip:
            _, encoded = cv2.imencode('.jpg', image, [int(cv2.IMWRITE_JPEG_QUALITY), 20])
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        Image.fromarray(image).save(path / view / ('%04d.png' % frame))
    with open(path / 'meta' / ('%04d.json' % frame), 'w') as outfile:
        json.dump(metadata, outfile, indent=4)
    with open(path / 'metric_info.json', 'w') as outfile:
        json.dump(metric_info, outfile, indent=4)


class ArtifactWriter:
    def __init__(self, write, max_pending=2):
        self._write = write
        self._queue = queue.Queue(maxsize=max_pending)
        self._error = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name='artifact-writer', daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                if self._error is None:
                    try:
                        self._write(item)
                    except Exception as exc:
                        self._error = exc
            finally:
                self._queue.task_done()

    def check(self):
        if self._error is not None:
            raise RuntimeError('Background artifact writing failed') from self._error

    def submit(self, item):
        if self._closed:
            raise RuntimeError('Artifact writer is closed')
        self.check()
        # Backpressure avoids unbounded memory growth when storage is slow.
        self._queue.put(item)
        self.check()

    def close(self):
        if not self._closed:
            self._closed = True
            self._queue.put(None)
            self._thread.join()
        self.check()
