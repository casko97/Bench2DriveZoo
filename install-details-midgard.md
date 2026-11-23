# Install Details
Make sure that Bench2Drive are checked out at 'origin/0.0.4', and that becnh2DriveZoo are based on 'uniad/vad-0.0.4'.

We use the IsaacSim compatible nodes to get rendering support.

## Nodes

These three GPUs have Ubuntu 22.04, Apptainer, and host NVIDIA Vulkan (libGLX_nvidia.so). nvidia-smi inside apptainer --nv is not enough; use the launchers below.

GPU overview:

| Node | GPUs | Constraint | Free Storage (Size  Used Avail Use%) | runtime per GPU (hours) |
|---|---|---|---|---|
| arwen | 10× RTX 3080 | `--constrain=arwen` | 7.0T  3.8T  2.9T  57% | 1,393 |
| isengard | 2× RTX 3080 | `--constrain=isengard` | 5.4T  363G  4.8T   7% | 1,486 |
| belegost | 10× RTX 2080 Ti | `--constrain=belegost` | | 1,467 |

Past two months usage:

| Node | Jobs | Completed | Other* | Total job runtime |
|---|---:|---:|---:|---:|
| `arwen` | 5,977 | 5,451 | 517 | 13,926.9 h |
| `isengard` | 659 | 529 | 128 | 2,971.8 h |
| `belegost` | 2,032 | 1,806 | 216 | 14,674.8 h |

Accounting for GPU count, Isengard has the lowest total runtime per GPU: about 1,486 hours per GPU, versus 1,393 for Arwen and 1,467 for Belegost.

**Useful commands:**
* Allocate gpu: `salloc --gres=gpu:1 --mem=5GB --cpus-per-task=4 --constrain=isengard`
* `/local_storage/users/casko` Personal storage on the node you’re working on

## Carla setup

Done in separate folder `/Midgard/home/casko/carla`

1. Create folder: `mkdir carla && cd carla`
2. Download: `wget -4 --server-response --progress=dot:giga --timeout=30 --tries=2 'https://carla-releases.s3.us-east-005.backblazeb2.com/Linux/CARLA_0.9.15.tar.gz'`
3. Unpack: `tar -xvf CARLA_0.9.15.tar.gz`
4. `cd Import && wget -4 --server-response --progress=dot:giga --timeout=30 --tries=2 'https://carla-releases.s3.us-east-005.backblazeb2.com/Linux/AdditionalMaps_0.9.15.tar.gz'`
5. `cd .. && bash ImportAssets.sh`

## Bench2Drive Repo Setup

1. Create venv: `conda create -n b2d_zoo.venv python=3.8`
2. Activate: `conda activate b2d_zoo.venv`
3. Setup GCC 11 and its paths:
    * Install: `mamba install -c conda-forge -c nvidia/label/cuda-11.8.0 'gcc_linux-64=11' 'gxx_linux-64=11'`
    * Locate and verify its compiler: `which gcc && which g++ && gcc --version && g++ --version`
    * Set CC and CXX to those paths before building: `export CC=/usr/bin/gcc && export CXX=/usr/bin/g++` 
        * echo after successful install gives: `/Midgard/home/casko/miniforge3/envs/b2d_zoo.venv/bin/x86_64-conda-linux-gnu-c++`
        * echo after successful install gives: /`Midgard/home/casko/miniforge3/envs/b2d_zoo.venv/bin/x86_64-conda-linux-gnu-cc`

4. Install CUDA 11.8 compiler and runtime development packages: 
    ```
    mamba install -n b2d_zoo.venv \
    -c nvidia/label/cuda-11.8.0 \
    -c conda-forge \
    --channel-priority flexible \
    'nvidia/label/cuda-11.8.0::cuda-nvcc=11.8.89' \
    'nvidia/label/cuda-11.8.0::cuda-cudart=11.8.89' \
    'nvidia/label/cuda-11.8.0::cuda-cudart-dev=11.8.89' \
    'nvidia/label/cuda-11.8.0::cuda-cccl=11.8.89'
    ```
5. Install PyTorch: 
    ````
    python -m pip install \
    torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 \
    --index-url https://download.pytorch.org/whl/cu118
    ```
6. Install more dependencies
    * Numerical packages: `python -m pip install --only-binary=:all: numpy==1.20.0 scipy==1.10.1 numba==0.48.0 llvmlite==0.31.0`
    * Build tools: `python -m pip install setuptools==75.3.4 wheel==0.45.1 ninja==1.13.2 packaging==26.2`
    * The rest: `python -m pip install -r requirements_midgard.txt "numpy==1.20.0"`
7. Set variables:
    * `export CUDA_HOME="$CONDA_PREFIX"` (echo after successful install gives: empty)
    * `export PATH="$CUDA_HOME/bin:$PATH"`
    * `export TORCH_CUDA_ARCH_LIST="7.5"` (echo after successful install gives: 7.5), 
    * **`TORCH_CUDA_ARCH_LIST="8.6"`for *Arwen* architectire**
    * `export MAX_JOBS=4`
    * `export CPATH="$CONDA_PREFIX/lib/python3.8/site-packages/nvidia/cusparse/include${CPATH:+:$CPATH}"`
    * Add the NVIDIA package include directories to the compiler’s search path: 
        ``` 
        for dir in "$CONDA_PREFIX"/lib/python3.8/site-packages/nvidia/*/include; do
        if [ -d "$dir" ]; then
            export CPATH="$dir${CPATH:+:$CPATH}"
        fi
        done
        ```
8. Install the repo: `python -m pip install -v --no-build-isolation --no-deps -e .`

Make sure the environment knows where Carla is: 
* `export CARLA_ROOT=/Midgard/home/casko/carla`
* `echo "$CARLA_ROOT/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg" >> /Midgard/home/casko/miniforge3/envs/b2d_zoo.venv/lib/python3.8/site-packages/carla.pth`



## Baseline Checkpoint

download pretrained weights:

Create directory: 
1. `mkdir ckpts` (under *'/local_storage/users/casko/'*)
2. Download VAD checkpoint: 
    ```
    wget -4 --server-response --progress=dot:giga --timeout=30 --tries=2 -c -P /local_storage/users/casko/cpts 'https://huggingface.co/rethinklab/Bench2DriveZoo/resolve/main/vad_b2d_base.pth'
    ```

## Dataset

**Preparations**
* Downgrade Pillow:  `uv pip install "Pillow==10.3.0"`

### Maps:
* Download maps: 
    ```
    curl -fsSL https://huggingface.co/api/datasets/rethinklab/Bench2Drive-Map/tree/main \
    | python -c 'import json,sys; print("\n".join(x["path"] for x in json.load(sys.stdin) if x["path"].endswith(".npz")))' \
    | while read -r file; do
        curl -fL --retry 5 --retry-all-errors \
            -O "https://huggingface.co/datasets/rethinklab/Bench2Drive-Map/resolve/main/$file"
        done
    ```
* Prepare maps: 
    ```
    cd mmcv/datasets && python prepare_B2D_mini.py --maps-only --map-root /local_storage/users/casko/dataset/maps --out-dir /local_storage/users/casko/dataset/infos
    ``` 
    This creates `b2d_map_infos.pkl` in the specified output directory. 
* To process one map at the time, pass: `--map Town11`
* Use `--maps-only` to process all maps without regenerating
route infos.

### Scenarios:

**v0.0.4**
* Download v0.0.4: `hf download rethinklab/Bench2Drive-V0.0.4 --repo-type dataset --local-dir /local_storage/users/casko/dataset/Bench2Drive-V0.0.4`
    ```
    curl -fsSL https://huggingface.co/api/datasets/rethinklab/Bench2Drive-V0.0.4/tree/main?recursive=true \
    | python -c 'import json,sys; print("\n".join(x["path"] for x in json.load(sys.stdin) if x["type"] == "file"))' \
    | while IFS= read -r file; do
        mkdir -p "$(dirname "$file")"
        curl -fL --retry 5 --retry-all-errors \
            -o "$file" \
            "https://huggingface.co/datasets/rethinklab/Bench2Drive-V0.0.4/resolve/main/$file" || break
        done
    ```
* Use the split manifest at `data/splits/bench2drive_train_val_split_v04.json`
* Extract the route archives and prepare their info files: 
    ```
    cd mmcv/datasets && python prepare_B2Dv004.py --extract --workers 6 --archive-dir /local_storage/users/casko/dataset/Bench2Drive-V0.0.4 --data-root /local_storage/users/casko/dataset/B2D-V0.0.4 --out-dir /local_storage/users/casko/dataset/infos --map-infos-pkl /local_storage/users/casko/dataset/infos/b2d_map_infos.pkl
    ```
* `prepare_B2Dv004.py` reuses `data/infos/b2d_map_infos.pkl`. Maps therefore need to be processed separately before running this.

## Open-loop eval

VAD open-loop eval does not need a running CARLA server. 

Submit from the repository
root. The script selects arwen and defaults to the checkpoint at
`/local_storage/users/casko/cpts/vad_b2d_base.pth`:

```bash
sbatch scripts/openloop_v004.sbatch
```

* The script requests one GPU, four CPUs and 16 GB RAM; adjust these and the
time limit with `sbatch` options as needed. 
* Slurm logs are written in the submission directory. 
* For a short smoke test, set `MAX_SAMPLES=10` before
submission. 
* The script activates the `b2d_zoo.venv` Conda environment before running Python.
* Set `CONDA_BASE`, `CONDA_ENV`, `DATA_ROOT`, `INFO_DIR`, `ANN_FILE`, `MAP_FILE`,
`WORKERS`, or `CHECKPOINT` to override the defaults in the script.
* The dataset root is the parent of `v0.0.4/`, not the version directory itself.

With the preparation command above, the evaluation paths are:

* `/local_storage/users/casko/dataset/B2D-V0.0.4/v0.0.4/`: extracted routes,
  including camera images for the validation routes.
* `/local_storage/users/casko/dataset/infos/b2d_infos_val_meta.pkl`: validation
  metadata, referring to per-route pickles in
  `/local_storage/users/casko/dataset/infos/b2d_infos_val/`.
* `/local_storage/users/casko/dataset/infos/b2d_map_infos.pkl`: prepared map data.

* The script checks that this directory exists. 
* The output metrics are printed to the Slurm log
* evaluation also writes results under `test/` in the repository. 
* `--out` is not used because this test entry point does not actually serialize the requested pickle.

## Closed-loop eval

This setup uses the separate 220-route v0.0.4 CARLA suite in `Bench2Drive/leaderboard/data/bench2drive_0.0.4_val.xml`. The launcher `train`, `val`, and `test` selections are deterministic local 60/20/20 development slices of that XML; `--split all` runs the complete 220-route suite. These closed-loop selections are independent of the upstream open-loop 1,056/44 route split.

### Setup one-time Bench2Drive links

The Bench2Drive evaluator must be able to import this checkout as
`Bench2DriveZoo` and load the VAD team agent. From the parent directory
containing both repositories, create these links:

```bash
cd /Midgard/home/casko/Bench2Drive
mkdir -p leaderboard/team_code
ln -s /Midgard/home/casko/Bench2DriveZoo Bench2DriveZoo
ln -s /Midgard/home/casko/Bench2DriveZoo/team_code/vad_b2d_agent.py leaderboard/team_code/vad_b2d_agent.py
ln -s /Midgard/home/casko/Bench2DriveZoo/team_code/pid_controller.py leaderboard/team_code/pid_controller.py
ln -s /Midgard/home/casko/Bench2DriveZoo/team_code/planner.py leaderboard/team_code/planner.py
```

The VAD agent, its configuration, and its checkpoint are then resolved as:

```text
leaderboard/team_code/vad_b2d_agent.py
Bench2DriveZoo/adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py
Bench2DriveZoo/ckpts/vad_b2d_base/vad_b2d_base.pth
```

Also set variables:
```
conda env config vars set -n b2d_zoo.venv BENCH2DRIVE_ROOT="$HOME/Bench2Drive" REPO_DIR="$HOME/Bench2DriveZoo"
```

### Run VAD on v0.0.4

`run_closed_loop_vad_cluster.sh` is a separate cluster launcher that reuses the existing evaluator and process supervision helpers.
* Logs are written to `vad-closed-<jobid>.out` and `.err`, and the evaluator writes a checkpoint JSON and `run.log` under `outputs/closed_loop`.
* Set `SAVE_VIEWS=rgb_front,bev` for saved images; the smoke test defaults to no saved views.

Request one node with two GPUs, 8 CPUs, 32 GiB system RAM, and two hours as a starting estimate. The two GPUs are allocated on the same node. CARLA needs a Vulkan-capable NVIDIA driver. The first allocated GPU is intended for CARLA, and the second is exposed to VAD using `CUDA_VISIBLE_DEVICES`.

**Smoke test.** For an interactive smoke test, obtain an allocation and inspect GPU mapping.

1. Allocate resources: `salloc --nodes=1 --ntasks=1 --gres=gpu:2 --mem=32G --cpus-per-task=8 --time=02:00:00 --constraint=arwen`
2. Check the allocation, Run: `python scripts/list_vulkan_adapters.py` and 
    ```
    hostname
    echo "$CUDA_VISIBLE_DEVICES"
    nvidia-smi --query-gpu=index,uuid,pci.bus_id,name,memory.total --format=csv
    ```
3. Set variables: 
    ```
    export BENCH2DRIVE_ROOT="/Midgard/home/casko/Bench2Drive"
    export CARLA_VULKAN_ADAPTER=0
    export CHECKPOINT=/local_storage/users/casko/cpts/vad_b2d_base.pth
    export REPO_DIR="/Midgard/home/casko/Bench2DriveZoo"
    ```
4. Launch one-scenario eval:
    ```bash
    bash scripts/closedloop_vad_one_scenario.sbatch
    ```