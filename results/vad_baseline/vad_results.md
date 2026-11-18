# VAD baseline results on Bench2Drive

## Open-loop v0.0.4 test split (ours)

| Item | Value |
| --- | --- |
| Model | VAD base |
| Checkpoint | `ckpts/vad_b2d_base/vad_b2d_base.pth` |
| Dataset | Bench2Drive v0.0.4, standard depth-free release |
| Split | Seeded 60/20/20 split, test partition (61 routes) |
| Evaluated frames | 13,587 |
| Config | `adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py` |
| Source log | [vad_v004_test.log](vad_v004_test.log) |

The v0.0.4 annotations were prepared without depth-based occlusion filtering because the standard release has no depth images.

#### Detection

| mAP | NDS | mATE | mASE | mAOE | mAVE |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.4507 | 0.5633 | 0.3934 | 0.2484 | 0.1509 | 0.3909 |

| Class | AP | ATE | ASE | AOE | AVE |
| --- | ---: | ---: | ---: | ---: | ---: |
| car | 0.290 | 0.241 | 0.107 | 0.024 | 1.148 |
| van | 0.182 | 0.401 | 0.480 | 0.031 | 0.060 |
| truck | 0.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bicycle | 0.668 | 0.297 | 0.089 | 0.041 | 0.659 |
| traffic sign | 0.435 | 0.286 | 0.020 | 0.036 | 0.008 |
| traffic cone | 0.784 | 0.348 | 0.137 | 0.025 | 0.008 |
| traffic light | 0.761 | 0.244 | 0.107 | 0.022 | 0.006 |
| pedestrian | 0.487 | 0.331 | 0.046 | 0.027 | 0.239 |

#### Motion prediction

| Actor | EPA | ADE | FDE | MR |
| --- | ---: | ---: | ---: | ---: |
| car | 0.8119 | 0.5846 | 0.6509 | 0.0566 |
| pedestrian | 0.3498 | 0.4141 | 0.4914 | 0.0160 |

#### Planning

| Metric | 1 s | 2 s | 3 s |
| --- | ---: | ---: | ---: |
| L2 error | 0.4375 | 0.9251 | 1.5284 |

Run command:

```bash
./adzoo/vad/dist_test.sh \
  ./adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py \
  ./ckpts/vad_b2d_base/vad_b2d_base.pth \
  1 \
  --cfg-options \
  data.test.ann_file=data/infos/v0.0.4/b2d_infos_test.pkl \
  data.test.map_file=data/infos/v0.0.4/b2d_map_infos.pkl
```

## Official repo results

The official repositories report the following VAD results. They use different Bench2Drive releases and evaluation protocols, so they should not be compared directly.

**Source/data provenance.** The Bench2DriveZoo table is on the `uniad/vad` branch (the result table was added on 2024-09-05). Its matching data-preparation guide identifies the offline data as the original **Bench2Drive Base `v1`** release (1,000 clips), using `bench2drive_base_train_val_split.json`. The VAD configuration evaluates open-loop data from the resulting
`b2d_infos_val.pkl` validation split. The official table itself does not attach an explicit Bench2Drive release tag to its closed-loop numbers; those are CARLA
route-benchmark results produced using the then-current post-2024-08-27 protocol, not results on the offline validation split.

### Open-loop

| Source / code version | Dataset and split | Model | Metric | Result |
| --- | --- | --- | --- | ---: |
| [Bench2DriveZoo `uniad/vad`](https://github.com/Thinklab-SJTU/Bench2DriveZoo/tree/uniad/vad), 2024 result table | Original Bench2Drive Base `v1` (1,000 clips), `b2d_infos_val.pkl` held-out validation split | VAD | L2 error at 2 s | 0.91 m |

### Closed-loop

| Source / benchmark version | Dataset / evaluation set | Model | Driving Score | Success Rate | Efficiency | Comfort |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| [Bench2Drive v0.0.4](https://github.com/Thinklab-SJTU/Bench2Drive/tree/0.0.4) | Bench2Drive v0.0.4 closed-loop benchmark (220-route evaluation set) | VAD | 38.65 | 17.27% | 163.74 | 67.34 |
| [Bench2DriveZoo `uniad/vad`](https://github.com/Thinklab-SJTU/Bench2DriveZoo/tree/uniad/vad), post-2024-08-27 protocol | Bench2Drive CARLA closed-loop route benchmark; the linked official VAD artifact has 213 route records | VAD | 42.35 | 15.00% | — | — |
| Bench2DriveZoo, deprecated pre-2024-08-27 protocol | Same Bench2Drive CARLA closed-loop route benchmark | VAD | 39.42 | 10.00% | — | — |

Bench2DriveZoo explicitly labels the parenthesized closed-loop values as
deprecated after bug fixes and protocol changes. Its parent Bench2Drive
evaluation documentation specifies a 220-route metric protocol, treating
missing routes as zero. Bench2Drive v0.0.4 is the official repository's current
benchmark table and is a different release/dataset from the original Base `v1`
offline split.

### Closed-loop multi-ability (Bench2Drive v0.0.4, 220-route evaluation set)

| Overtaking | Merging | Emergency brake | Give way | Traffic signs | Mean |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 13.04% | 17.19% | 29.82% | 16.67% | 19.77% | 19.30% |
