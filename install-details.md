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

Save to log:
```
./scripts/run_closed_loop_vad_v004.sh --one-scenario 2>&1 | tee closed_loop.log
```

Each fresh run gets a timestamped JSON checkpoint and artifact directory under `/home/casko/phd-code/Bench2DriveZoo/outputs/closed_loop` by default.

#### One-scenario smoke test

[`one_scenario_town07.xml`](./one_scenario_town07.xml) contains official route `24948` on `Town07`, with a signalized right turn in daylight and dry weather. It was extracted from `Bench2Drive/leaderboard/data/bench2drive_0.0.4_val.xml`, preserving the route and scenario parameters. The previous Town02 and Town12 routes remain available in `one_scenario_town02.xml` and `one_scenario.xml`.

From the Bench2DriveZoo repository root, run:

```bash
./scripts/run_closed_loop_vad_v004.sh --one-scenario
```

* `--one-scenario` selects the one-route XML and disables development splitting.
* The evaluator launches CARLA automatically with offscreen rendering; no separate CARLA window is needed.
* To save terminal output, append `2>&1 | tee closed_loop.log` to the launch command.
* Every 30 seconds, CPU and memory load for the host, GPU utilization and memory, and timing measurements are printed and appended to `telemetry.jsonl`
* The launcher uses the VAD agent and checkpoint configured above. 

Image sequences and per-frame data are saved in the printed artifact directory:
- PNGs from six cameras: front, front-left, front-right, back, back-left, and back-right.
- A BEV visualization as bev/*.png.
- Per-frame metadata as meta/*.json, plus metric_info.json.
After evaluation finishes, the launcher creates a looping GIF for each camera and BEV PNG sequence (for example, `rgb_front.gif` and `bev.gif` beside their frame directories). It uses `ffmpeg`, scales GIFs to at most 960 pixels wide, and encodes them at 10 fps. `ffmpeg` must be available on `PATH`; otherwise the launcher reports that GIF creation was skipped. The numbered PNG frames remain available. The checkpoint JSON contains route scores and metrics. No MP4 is created.

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


