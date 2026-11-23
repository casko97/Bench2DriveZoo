import copy
import os
import unittest

from team_code.vad_fast_pipeline import (SingleAugmentation,
                                         collate_single_vad,
                                         enable_single_augmentation)


class Container:
    def __init__(self, data, stack=False, cpu_only=False):
        self.data, self.stack, self.cpu_only = data, stack, cpu_only


class Tensor:
    def __init__(self, value):
        self.value = value

    def unsqueeze(self, dim):
        assert dim == 0
        return Tensor([self.value])


class VadFastPipelineTests(unittest.TestCase):
    def test_single_collation_and_fallback(self):
        values = {'img_metas': [Container({'frame_idx': 2}, cpu_only=True)],
                  'img': [Container(Tensor('images'), stack=True)],
                  'ego_fut_cmd': [Container(Tensor('command'), stack=True)]}
        fallback = lambda batch, samples_per_gpu: 'fallback'
        batch = collate_single_vad(values, fallback, Container, Tensor)
        self.assertEqual(batch['img_metas'], [[{'frame_idx': 2}]])
        self.assertEqual(batch['img'][0].value, ['images'])
        self.assertEqual(batch['ego_fut_cmd'][0].value, ['command'])
        values['extra'] = []
        self.assertEqual(collate_single_vad(values, fallback, Container, Tensor), 'fallback')

    def test_single_augmentation_preserves_input_and_fields(self):
        class Transform:
            def __call__(self, data):
                data['img'] = [image + 1 for image in data['img']]
                return data
        class Aug:
            transforms = Transform()
            img_scale = [(1600, 900)]
            pts_scale_ratio = [1.0]
            flip_direction = ['horizontal']
        original = {'img': [1, 2], 'scene_token': 'scene'}
        before = copy.deepcopy(original)
        output = SingleAugmentation(Aug())(original)
        self.assertEqual(original, before)
        self.assertEqual(output['img'], [[2, 3]])
        self.assertEqual(output['flip'], [False])
        self.assertEqual(output['scale'], [(1600, 900)])

    def test_other_pipeline_is_not_rewritten(self):
        class Pipeline:
            transforms = [object()]
        self.assertFalse(enable_single_augmentation(Pipeline()))

    def test_real_pipeline_matches_original(self):
        try:
            import numpy as np
            import torch
            from mmcv import Config
            from mmcv.datasets.pipelines import Compose
            from mmcv.datasets.pipelines import transforms_3d
            from mmcv.image.photometric import imnormalize, imnormalize_
            from mmcv.parallel.collate import collate
            from mmcv.parallel.data_container import DataContainer
        except ImportError as exc:
            if os.environ.get('VAD_REQUIRE_RUNTIME_TEST') == '1':
                raise
            self.skipTest('VAD runtime dependencies unavailable: {}'.format(exc))

        config_path = os.path.join(os.path.dirname(__file__), '..', 'adzoo',
                                   'vad', 'configs', 'VAD', 'VAD_base_e2e_b2d.py')
        config = Config.fromfile(config_path)
        definitions = [item for item in config.inference_only_pipeline
                       if item['type'] not in ('LoadMultiViewImageFromFiles',
                                               'LoadMultiViewImageFromFilesInCeph')]
        reference, fast = Compose(definitions), Compose(definitions)
        self.assertTrue(enable_single_augmentation(fast))

        def check_equal(left, right):
            self.assertIs(type(left), type(right))
            if isinstance(left, torch.Tensor):
                self.assertEqual(left.dtype, right.dtype)
                self.assertEqual(left.shape, right.shape)
                self.assertTrue(torch.equal(left, right))
            elif isinstance(left, np.ndarray):
                self.assertEqual(left.dtype, right.dtype)
                np.testing.assert_array_equal(left, right)
            elif isinstance(left, dict):
                self.assertEqual(left.keys(), right.keys())
                for key in left:
                    check_equal(left[key], right[key])
            elif isinstance(left, (list, tuple)):
                self.assertEqual(len(left), len(right))
                for a, b in zip(left, right):
                    check_equal(a, b)
            else:
                self.assertEqual(left, right)

        rng = np.random.RandomState(4)
        # Compare against the previous implementation, including inputs that
        # are already float32 and non-contiguous views.
        def previous_normalize(img, mean, std, to_rgb=True):
            return imnormalize_(img.copy().astype(np.float32), mean, std, to_rgb)

        mean = np.array([123.675, 116.28, 103.53], dtype=np.float32)
        std = np.array([58.395, 57.12, 57.375], dtype=np.float32)
        base = rng.randint(0, 256, (17, 19, 3), dtype=np.uint8)
        for image in (base, base.astype(np.float32), base.astype(np.float64),
                      base[:, ::2, :], base[::-1], base.transpose(1, 0, 2)):
            for to_rgb in (False, True):
                original = image.copy()
                expected_image = previous_normalize(image, mean, std, to_rgb)
                actual_image = imnormalize(image, mean, std, to_rgb)
                np.testing.assert_array_equal(expected_image, actual_image)
                np.testing.assert_array_equal(image, original)
                self.assertFalse(np.shares_memory(actual_image, image))

        # Include the actual CARLA camera resolution as well as small cases
        # with and without initial padding.
        for height, width in ((65, 97), (64, 96), (900, 1600)):
            with self.subTest(height=height, width=width):
                sample = {'img': [rng.randint(0, 256, (height, width, 3), dtype=np.uint8)
                                  for _ in range(6)],
                          'lidar2img': np.stack([np.eye(4) for _ in range(6)]),
                          'ego_fut_cmd': np.array([0., 0., 1., 0., 0., 0.]),
                          'scene_token': 'test', 'frame_idx': 3,
                          'can_bus': np.arange(18, dtype=np.float64)}
                # Compare the fast path to the original normalization as well
                # as the original augmentation and collation.
                saved_normalize = transforms_3d.imnormalize
                try:
                    transforms_3d.imnormalize = previous_normalize
                    expected = collate([reference(copy.deepcopy(sample))], samples_per_gpu=1)
                finally:
                    transforms_3d.imnormalize = saved_normalize
                def unexpected_fallback(*args, **kwargs):
                    self.fail('Fast collation unexpectedly fell back to the original')
                actual = collate_single_vad(fast(copy.deepcopy(sample)), unexpected_fallback,
                                            DataContainer, torch.Tensor)
                check_equal(expected, actual)


if __name__ == '__main__':
    unittest.main()
