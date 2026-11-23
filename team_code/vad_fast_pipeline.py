"""Copy-saving helpers for the single-sample VAD evaluation pipeline."""


class SingleAugmentation:
    """Run the known VAD transforms without copying their input images.

    These transforms replace images and metadata rather than mutating their
    inputs. The original augmentation object remains the fallback for other
    configurations.
    """

    def __init__(self, augmentation):
        self.transforms = augmentation.transforms
        self.scale = augmentation.img_scale[0]
        self.pts_scale_ratio = augmentation.pts_scale_ratio[0]
        self.flip_direction = augmentation.flip_direction[0]

    def __call__(self, results):
        data = results.copy()
        data.update(scale=self.scale, flip=False,
                    pcd_scale_factor=self.pts_scale_ratio,
                    flip_direction=self.flip_direction,
                    pcd_horizontal_flip=False, pcd_vertical_flip=False)
        data = self.transforms(data)
        return {key: [value] for key, value in data.items()}


def enable_single_augmentation(pipeline):
    """Only specialize the exact transform sequence used by VAD inference."""
    transforms = pipeline.transforms
    if [type(t).__name__ for t in transforms] != [
        'NormalizeMultiviewImage', 'PadMultiViewImage', 'MultiScaleFlipAug3D'
    ]:
        return False
    aug = transforms[2]
    if (aug.flip or len(aug.img_scale) != 1 or len(aug.pts_scale_ratio) != 1
            or len(aug.flip_direction) != 1):
        return False
    if [type(t).__name__ for t in aug.transforms.transforms] != [
        'RandomScaleImageMultiViewImage', 'PadMultiViewImage',
        'VADFormatBundle3D', 'CustomCollect3D'
    ]:
        return False
    transforms[2] = SingleAugmentation(aug)
    return True


def collate_single_vad(results, fallback, data_container, tensor_type):
    """Collate the standard one-sample VAD input without padding or copies."""
    if set(results) != {'img_metas', 'img', 'ego_fut_cmd'}:
        return fallback([results], samples_per_gpu=1)
    for key in results:
        value = results[key]
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], data_container):
            return fallback([results], samples_per_gpu=1)
    meta, img, cmd = (results[key][0] for key in ('img_metas', 'img', 'ego_fut_cmd'))
    if (not meta.cpu_only or not img.stack or img.cpu_only or not cmd.stack
            or cmd.cpu_only or not isinstance(img.data, tensor_type)
            or not isinstance(cmd.data, tensor_type)):
        return fallback([results], samples_per_gpu=1)
    return {'img_metas': [[meta.data]], 'img': [img.data.unsqueeze(0)],
            'ego_fut_cmd': [cmd.data.unsqueeze(0)]}
