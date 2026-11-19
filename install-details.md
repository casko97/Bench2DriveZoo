# Install Details
Make sure that Bench2Drive are checked out at 'origin/0.0.4', and that becnh2DriveZoo are based on 'uniad/vad-0.0.4'.

## Carla setup

Done in separate folder `/home/casko/phd-code/Carla` (globally, no venv)

1. Create folder: `mkdir carla && cd carla`
2. Download: `wget -4 --server-response --progress=dot:giga --timeout=30 --tries=2 'https://carla-releases.s3.us-east-005.backblazeb2.com/Linux/CARLA_0.9.15.tar.gz'`
3. Unpack: `tar -xvf CARLA_0.9.15.tar.gz`
4. `cd Import && wget -4 --server-response --progress=dot:giga --timeout=30 --tries=2 'https://carla-releases.s3.us-east-005.backblazeb2.com/Linux/AdditionalMaps_0.9.15.tar.gz'`
5. `cd .. && bash ImportAssets.sh`

## Bench2Drive Repo Setup

1. Create venv: `uv venv b2d_zoo.venv python=3.8`
2. Activate: `source b2d_zoo.venv/bin/activate`
2. Set CUDA toolkit variables: `export CUDA_HOME=/usr/local/cuda-11.8` and `export PATH="$CUDA_HOME/bin:$PATH"`
3. Install torch: `uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118`
4. Install ninja and packaging: `uv pip install setuptools ninja packaging`
5. Set some more variables: `export CC=/usr/bin/gcc-11`, `export CXX=/usr/bin/g++-11`, and `export TORCH_CUDA_ARCH_LIST=6.1`
6. Install repo: `export MAX_JOBS=4 && uv pip install -v --no-build-isolation -e .`

Make sure the environment knows where Carla is:
* `export CARLA_ROOT=/home/casko/phd-code/Carla`
* `echo "$CARLA_ROOT/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg" >> /home/casko/phd-code/Bench2DriveZoo/b2d_zoo.venv/lib/python3.8/site-packages/carla.pth`

*(Last point instead of: "Important!!! Otherwise, the python environment can not find carla package
`echo "$CARLA_ROOT/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg" >> YOUR_CONDA_PATH/envs/YOUR_CONDA_ENV_NAME/lib/python3.8/site-packages/carla.pth` # python 3.8 also works well, please set YOUR_CONDA_PATH and YOUR_CONDA_ENV_NAME")*

Finally, download pretrained weights:
1. Create directory: `mkdir ckpts`
Download VAD checkpoint: `wget -4 --server-response --progress=dot:giga --timeout=30 --tries=2 -c -P /home/casko/phd-code/Bench2DriveZoo/ckpts 'https://huggingface.co/rethinklab/Bench2DriveZoo/resolve/main/vad_b2d_base.pth'`

## Once a venv is available

Activate venv: `source b2d_zoo.venv/bin/activate`

## Dataset Setup

* Install HF-cli: `pip install --upgrade huggingface_hub`
* Downgrade Pillow:  `uv pip install "Pillow==10.3.0"`

### Maps:
* Download maps: `HF_HUB_VERBOSITY=info HF_DEBUG=1 hf download rethinklab/Bench2Drive-Map --repo-type dataset --local-dir data/bench2drive/maps --max-workers 4`
* Prepare maps: `cd mmcv/datasets && python -c "from prepare_B2D_mini import gengrate_map, MAP_ROOT; gengrate_map(MAP_ROOT)"`. This should create `data/infos/b2d_map_infos.pkl`
* To proces the heavier maps (11,12,13), use the streaming option: `cd mmcv/datasets && python prepare_B2D_streaming.py --map Town11 --stream-map-archive`
* To process one map at the time, pass: `--map Town11`
* Use `--maps-only` to process all maps without regenerating
route infos.

#### Big maps

To be able to process the big maps (11,12,13), increase swap memory:
```
sudo fallocate -l 32G /swap-b2d-temp
sudo chmod 600 /swap-b2d-temp
sudo mkswap /swap-b2d-temp
sudo swapon -p 10 /swap-b2d-temp
```
Restore afterward:
```
sudo swapoff /swap-b2d-temp
sudo rm /swap-b2d-temp
```

### Scenarios:

#### mini
* Run download script (mini split): `./download_scripts/download_mini.sh`
* Unpack dataset into `data/bench2drive/mini` (use `tar -xvf`)
* Prepare dataset: `cd mmcv/datasets && python prepare_B2D_mini.py python prepare_B2D_mini.py --workers 4 --shared-split --skip-map` (see [repo](https://github.com/Thinklab-SJTU/Bench2DriveZoo/blob/uniad/vad/docs/DATA_PREP.md)). 
* This uses all ten mini routes as both train and validation.
* It reuses `data/infos/b2d_map_infos.pkl`. Maps therefore need to be processed separately before running this

#### v0.0.4
* Download v0.0.4: `hf download rethinklab/Bench2Drive-V0.0.4 --repo-type dataset --local-dir Bench2Drive-V0.0.4`
* Use the split manifest at `data/splits/bench2drive_train_val_split_v04.json`
* Extract the route archives and prepare their info files: `cd mmcv/datasets && python prepare_B2Dv004.py --extract --workers 6`.
  Extracted routes are placed in `data/bench2drive/v0.0.4`; generated per-route info files and metadata are written to `data/infos/v0.0.4/b2d_infos_{train,val}/` and `b2d_infos_{train,val}_meta.pkl`.
  The standard v0.0.4 release has no depth images, so its depth-based occlusion filter is disabled by default.
* `prepare_B2Dv004.py` reuses `data/infos/b2d_map_infos.pkl`. Maps therefore need to be processed separately before running this.

**Official v0.0.4 split.** With the complete 1,100-route release, this is 1,056 training routes and 44 validation routes. There is no open-loop test split. The distinct 220-route CARLA XML is the closed-loop benchmark.

## Open-loop eval

**Run openloop eval (v0.0.4):** Use `--split val` for the official 44-route validation set; `--split train` selects all non-validation routes. Add `--max-samples N` to evaluate only the first N samples, for example `--split val --max-samples 2` for a bounded smoke run.
```
./adzoo/vad/dist_test.sh \
  ./adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py \
  ./ckpts/vad_b2d_base/vad_b2d_base.pth \
  1 --split val
  ```

**Run open-loop eval (mini):** After preparing mini with `--shared-split`, use the mini image root and generated validation metadata. This evaluates all ten mini routes.
```
./adzoo/vad/dist_test.sh \
  ./adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py \
  ./ckpts/vad_b2d_base/vad_b2d_base.pth \
  1 --split val --cfg-options \
  data.val.ann_file=data/infos/b2d_infos_val.pkl \
  data.val.use_separated_clip_data=False
```

## Closed-loop eval

This setup uses the separate 220-route v0.0.4 CARLA suite in `Bench2Drive/leaderboard/data/bench2drive_0.0.4_val.xml`. The launcher `train`, `val`, and `test` selections are deterministic local 60/20/20 development slices of that XML; `--split all` runs the complete 220-route suite. These closed-loop selections are independent of the upstream open-loop 1,056/44 route split.

### Setup one-time Bench2Drive links

The Bench2Drive evaluator must be able to import this checkout as
`Bench2DriveZoo` and load the VAD team agent. From the parent directory
containing both repositories, create these links:

```bash
cd /home/casko/phd-code/Bench2Drive
mkdir -p leaderboard/team_code
ln -s /home/casko/phd-code/Bench2DriveZoo Bench2DriveZoo
ln -s /home/casko/phd-code/Bench2DriveZoo/team_code/vad_b2d_agent.py leaderboard/team_code/vad_b2d_agent.py
ln -s /home/casko/phd-code/Bench2DriveZoo/team_code/pid_controller.py leaderboard/team_code/pid_controller.py
ln -s /home/casko/phd-code/Bench2DriveZoo/team_code/planner.py leaderboard/team_code/planner.py
```

The VAD agent, its configuration, and its checkpoint are then resolved as:

```text
leaderboard/team_code/vad_b2d_agent.py
Bench2DriveZoo/adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py
Bench2DriveZoo/ckpts/vad_b2d_base/vad_b2d_base.pth
```

### Run VAD on v0.0.4

The dedicated launcher activates `b2d_zoo.venv`, exports
`CARLA_ROOT=/home/casko/phd-code/Carla`, and invokes the official Bench2Drive
evaluator on all 220 routes by default:

```bash
./scripts/run_closed_loop_vad_v004.sh
```

The launcher displays console output and appends it to `run.log` in the run's artifact directory once that directory has been determined. Resumed runs append to the same log when using the same artifact directory.

Each fresh run gets a timestamped JSON checkpoint and artifact directory under `/home/casko/phd-code/Bench2DriveZoo/outputs/closed_loop` by default.

#### One-scenario smoke test

[`one_scenario_town07.xml`](./one_scenario_town07.xml) contains official route `24948` on `Town07`, with a signalized right turn in daylight and dry weather. It was extracted from `Bench2Drive/leaderboard/data/bench2drive_0.0.4_val.xml`, preserving the route and scenario parameters. The previous Town02 and Town12 routes remain available in `one_scenario_town02.xml` and `one_scenario.xml`.

From the Bench2DriveZoo repository root, run:

```bash
./scripts/run_closed_loop_vad_v004.sh --one-scenario
```

* `--one-scenario` selects the one-route XML and disables development splitting.
* The evaluator launches CARLA automatically with offscreen rendering; no separate CARLA window is needed.
* Ctrl+C requests a graceful stop. If cleanup does not finish within 15 seconds, the launcher force-stops the evaluator and its child processes. Press Ctrl+C a second time to force immediately. Statistics still held in memory may be lost during a forced stop.
* Console output is also saved to `run.log` in the artifact directory.
* Every 30 seconds, CPU and memory load for the host, GPU utilization and memory, and timing measurements are printed and appended to `telemetry.jsonl`
* Benchmark events, including recorded collisions and blocked-vehicle events, are appended to `live_events.jsonl` as they occur. Ongoing events may be updated; the final checkpoint remains the authoritative result.
* By default, the launcher stops a route after the first collision recorded by the benchmark. Set `SUSTAINED_COLLISION_FRAMES=0` to disable this early stop for the standard benchmark protocol, or set it to a higher count of consecutive simulation frames with collision callbacks against the same actor. CARLA may not emit callbacks every frame of physical contact. The stop reason is written to `live_events.jsonl`; partial route statistics are saved through the normal evaluator cleanup.
* The launcher uses the VAD agent and checkpoint configured above. 
* The launcher saves front and overhead images by default. Set `SAVE_VIEWS=all` to save all seven views, choose a comma-separated list such as `SAVE_VIEWS=rgb_front,rgb_front_left`, or use `SAVE_VIEWS=` to save no images. Model camera inputs are unchanged.
* Set `SAVE_JPEG_ROUNDTRIP=0` to skip the quality-20 JPEG encode/decode step for saved camera images. The output files remain losslessly compressed PNGs; the default `1` preserves the existing JPEG artifacts. This setting does not affect model inputs or the BEV image.

Image sequences and per-frame data are saved in the printed artifact directory:
- By default, front-camera PNGs and an overhead BEV visualization as bev/*.png. Other camera views can be selected using `SAVE_VIEWS`.
- Per-frame metadata as meta/*.json, plus metric_info.json.
After evaluation finishes, the launcher creates a looping GIF for each camera and BEV PNG sequence (for example, `rgb_front.gif` and `bev.gif` beside their frame directories). It uses `ffmpeg`, scales GIFs to at most 960 pixels wide, and encodes them at 10 fps. `ffmpeg` must be available on `PATH`; otherwise the launcher reports that GIF creation was skipped. The numbered PNG frames remain available. The checkpoint JSON contains route scores and metrics. No MP4 is created.

#### Launcher configuration

From the repository root, start a one-route evaluation with:

```bash
./scripts/run_closed_loop_vad_v004.sh --one-scenario
```

The launcher accepts the following command-line options. Options are processed in order, so a later option can override an earlier one.

| Option | Behavior |
| --- | --- |
| `--one-scenario` | Select `one_scenario_town07.xml` and set the split to `all`. |
| `--routes PATH` | Select a routes XML; overrides `ROUTES`. `--routes=PATH` also works. |
| `--split SPLIT` | Select `train`, `val`, `test`, or `all`; overrides `SPLIT`. `--split=SPLIT` also works. |
| `--checkpoint PATH` | Resume an existing checkpoint JSON; overrides `CHECKPOINT_ENDPOINT`. `--checkpoint=PATH` also works. |

Environment variables can be set before the command, for example:

```bash
SAVE_JPEG_ROUNDTRIP=0 SAVE_VIEWS=rgb_front,bev ./scripts/run_closed_loop_vad_v004.sh --one-scenario
```

| Variable | Default | Behavior |
| --- | --- | --- |
| `BENCH2DRIVE_ROOT` | `../Bench2Drive` relative to this repository | Bench2Drive checkout; relative route, checkpoint, and artifact paths are resolved here. |
| `B2D_ZOO_VENV` | `b2d_zoo.venv` in this repository | Python environment activated by the launcher. |
| `CARLA_ROOT` | `../Carla` relative to this repository | CARLA installation. |
| `GPU_RANK` | `0` | Physical GPU selected for the evaluator and CARLA. |
| `ROUTES` | `leaderboard/data/bench2drive_0.0.4_val.xml` | Routes XML. |
| `SPLIT` | `all` | `all` uses all selected routes; `train`, `val`, and `test` select deterministic local 60/20/20 subsets. These are not the upstream dataset splits. |
| `CHECKPOINT_ENDPOINT` | unset | Existing checkpoint JSON to resume; without it, a fresh timestamped checkpoint is created under `outputs/closed_loop`. Resume with the same routes, split, and custom artifact path as the original run. |
| `SAVE_PATH` | A directory named after the checkpoint beside its JSON | Directory for run artifacts and telemetry. |
| `SAVE_VIEWS` | `rgb_front,bev` | Comma-separated saved views: `rgb_front`, `rgb_front_left`, `rgb_front_right`, `rgb_back`, `rgb_back_left`, `rgb_back_right`, `bev`; use `all` for all views or an empty value for none. Images are saved every ten steps. This does not select model inputs. |
| `SAVE_JPEG_ROUNDTRIP` | `1` | Set to `0` to skip the quality-20 JPEG encode/decode for saved camera images. Outputs remain PNGs; model inputs and BEV are unaffected. |
| `PLANNER_TYPE` | `only_traj` | Planner setting exported to the evaluator and agent. |
| `TEAM_AGENT` | `leaderboard/team_code/vad_b2d_agent.py` | Agent path relative to the Bench2Drive checkout. |
| `TEAM_CONFIG` | `Bench2DriveZoo/adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py+Bench2DriveZoo/ckpts/vad_b2d_base/vad_b2d_base.pth` | Agent configuration and checkpoint, separated by `+`. The launcher also checks that the default VAD checkpoint exists. |
| `SUSTAINED_COLLISION_FRAMES` | `1` | Stop a route after this many consecutive collision callback frames for the same actor, starting with a benchmark-recorded collision. Set `0` to disable this early stop. |
| `RECORD_PATH` | unset | Passed to the evaluator's CARLA recording option. |
| `TMPDIR` | `/tmp` | Directory for temporary split route XML files. |
| `PYTHONPATH` | existing value, if any | The launcher appends the CARLA and Bench2Drive paths. |

The launcher fixes the CARLA and traffic-manager ports to `30000` and `50000`, enables telemetry, and uses one repetition. Console output is shown in the terminal and appended to `run.log` under `SAVE_PATH` once the artifact path has been determined. Telemetry and live events are also written there; if `ffmpeg` is available, GIFs are generated after evaluation. Changes to environment variables apply when a new run starts.

#### More options

* To resume from an existing checkpoint, pass its path with `--checkpoint` (or
set `CHECKPOINT_ENDPOINT`). The launcher detects the existing JSON and resumes
automatically. For example:

    ```bash
    # Uses the launcher's default route XML and the full 220-route suite.
    # For a checkpoint from custom routes, pass the same ROUTES and SPLIT values used before.
    # If the original run used a custom SAVE_PATH, pass that same SAVE_PATH again.
    ./scripts/run_closed_loop_vad_v004.sh \
    --checkpoint /home/casko/phd-code/Bench2DriveZoo/outputs/closed_loop/eval_vad_v0.0.4_all_YYYYMMDD_HHMMSS_NNNNNNNNN.json
    ```

* To point the launcher at a different compatible CARLA XML:

    ```bash
    ./scripts/run_closed_loop_vad_v004.sh \
      --routes leaderboard/data/routes_devtest.xml --split all
    ```

* Use `--split train`, `--split val`, or `--split test` for deterministic local
development slices. The same option can be set with the `SPLIT` environment
variable. *(These are not the upstream open-loop dataset splits.)*

* Change `GPU_RANK` to select a different physical GPU.


## Runtime (2026-11-19)
On the local GTX 1080 Ti, a feedback-pipeline smoke run with `SAVE_VIEWS=` and `--one-scenario` took approximately 197 seconds of route execution for 10.65 seconds of simulated time (about 0.054× real time). 

It ended early after a collision, so this is not the runtime of a completed route or a benchmark throughput estimate. Telemetry during the run showed roughly 0.9 seconds per simulation step and 9–10 GiB of GPU memory in use. 
