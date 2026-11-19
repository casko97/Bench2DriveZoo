"""Run Garage's local evaluator with independent ego-attached video cameras."""
import json
import os
import queue
import runpy
import subprocess
import sys
import threading
from pathlib import Path

import carla
import cv2
import numpy as np
from leaderboard.scenarios.scenario_manager_local import ScenarioManager
from srunner.scenariomanager.carla_data_provider import CarlaDataProvider


class CameraRecorder:
    def __init__(self, world, ego, root, name, transform):
        self.path = root / name
        self.path.mkdir(parents=True, exist_ok=False)
        self.name = name
        self.frames = []
        self.dropped = 0
        self.error = None
        self.queue = queue.Queue(maxsize=128)
        self.thread = threading.Thread(target=self.write_frames, daemon=True)
        self.thread.start()
        bp = world.get_blueprint_library().find('sensor.camera.rgb')
        for key, value in {'image_size_x': '640', 'image_size_y': '360', 'fov': '90', 'sensor_tick': '0.1'}.items():
            bp.set_attribute(key, value)
        self.sensor = world.spawn_actor(bp, transform, attach_to=ego)
        self.sensor.listen(self.capture)

    def capture(self, image):
        try:
            self.queue.put_nowait((image.frame, image.timestamp, bytes(image.raw_data), image.height, image.width))
        except queue.Full:
            self.dropped += 1

    def write_frames(self):
        try:
            while True:
                item = self.queue.get()
                if item is None:
                    return
                frame, timestamp, raw, height, width = item
                image = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))[:, :, :3]
                path = self.path / ('{:06d}.png'.format(len(self.frames)))
                if not cv2.imwrite(str(path), image):
                    raise RuntimeError('failed to write {}'.format(path))
                self.frames.append({'frame': frame, 'simulation_time': timestamp})
        except Exception as exc:
            self.error = repr(exc)

    def close(self):
        self.sensor.stop()
        self.sensor.destroy()
        self.queue.put(None)
        self.thread.join(timeout=120)
        if self.thread.is_alive():
            self.error = 'writer did not finish'
        video = self.path.parent / (self.name + '.mp4')
        if self.frames and not self.error:
            result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                                     '-framerate', '10', '-i', str(self.path / '%06d.png'),
                                     '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
                                     '-movflags', '+faststart', str(video)])
            if result.returncode:
                self.error = 'ffmpeg exit {}'.format(result.returncode)
        return {'camera': self.name, 'frames': self.frames, 'dropped': self.dropped,
                'error': self.error, 'video': str(video) if video.exists() else None}


recorders = []
video_root = Path(os.environ['PDM_VIDEO_DIR']).resolve()
video_root.mkdir(parents=True, exist_ok=True)
original_load = ScenarioManager.load_scenario
original_stop = ScenarioManager.stop_scenario


def load_with_video(self, *args, **kwargs):
    result = original_load(self, *args, **kwargs)
    world = CarlaDataProvider.get_world()
    ego = self.ego_vehicles[0]
    recorders.append(CameraRecorder(world, ego, video_root, 'chase',
        carla.Transform(carla.Location(x=-6, z=3.2), carla.Rotation(pitch=-12))))
    recorders.append(CameraRecorder(world, ego, video_root, 'overhead',
        carla.Transform(carla.Location(z=25), carla.Rotation(pitch=-90))))
    return result


def stop_with_video(self, *args, **kwargs):
    try:
        return original_stop(self, *args, **kwargs)
    finally:
        metadata = [recorder.close() for recorder in recorders]
        (video_root / 'video_metadata.json').write_text(json.dumps(metadata, indent=2))
        for item in metadata:
            print('[video] {} frames={} dropped={} error={} file={}'.format(
                item['camera'], len(item['frames']), item['dropped'], item['error'], item['video']), flush=True)


ScenarioManager.load_scenario = load_with_video
ScenarioManager.stop_scenario = stop_with_video
script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name='__main__')
