# VAD baseline results on Bench2Drive

## Open-loop v0.0.4 validation split

| Item | Value |
| --- | --- |
| Model | VAD base |
| Checkpoint | `/local_storage/users/casko/cpts/vad_b2d_base.pth` |
| Dataset | Bench2Drive v0.0.4 |
| Split | Validation (11,414 frames) |
| Evaluated frames | 11,414 |
| Config | `adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py` |
| Source log | [vad-v004-1252692.out](vad-v004-1252692.out) |

The log reports inference-speed-only mode. Per-route metadata and annotations were loaded from the paths shown in the source log.

#### Detection

| mAP | NDS | mATE | mASE | mAOE | mAVE |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.4443 | 0.5396 | 0.4359 | 0.2518 | 0.1537 | 0.5236 |

| Class | AP | ATE | ASE | AOE | AVE |
| --- | ---: | ---: | ---: | ---: | ---: |
| car | 0.337 | 0.231 | 0.071 | 0.021 | 1.473 |
| van | 0.059 | 0.403 | 0.307 | 0.017 | 0.859 |
| truck | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bicycle | 0.607 | 0.297 | 0.114 | 0.053 | 0.646 |
| traffic sign | 0.457 | 0.266 | 0.024 | 0.031 | 0.008 |
| traffic cone | 0.728 | 0.284 | 0.268 | 0.033 | 0.009 |
| traffic light | 0.706 | 0.258 | 0.172 | 0.020 | 0.006 |
| pedestrian | 0.660 | 0.749 | 0.059 | 0.055 | 0.187 |

#### Motion prediction

| Actor | EPA | ADE | FDE | MR |
| --- | ---: | ---: | ---: | ---: |
| car | 0.7955 | 0.7690 | 0.8729 | 0.0863 |
| pedestrian | 0.3223 | 0.2977 | 0.3214 | 0.0146 |

#### Planning

| Metric | 1 s | 2 s | 3 s |
| --- | ---: | ---: | ---: |
| L2 error | 0.4650 | 0.9289 | 1.4808 |
| Object collision rate | 0.0000 | 0.0000 | 0.0000 |
| Object box collision rate | 0.0072 | 0.0096 | 0.0117 |

## Official Open-loop Results

| Source / code version | Dataset and split | Model | Metric | Result |
| --- | --- | --- | --- | ---: |
| [Bench2DriveZoo `uniad/vad`](https://github.com/Thinklab-SJTU/Bench2DriveZoo/tree/uniad/vad), 2024 result table | Original Bench2Drive Base `v1` (1,000 clips), `b2d_infos_val.pkl` held-out validation split | VAD | L2 error at 2 s | 0.91 m |

