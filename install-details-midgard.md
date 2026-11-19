# Install Details
Make sure that Bench2Drive are checked out at 'origin/0.0.4', and that becnh2DriveZoo are based on 'uniad/vad-0.0.4'.

We use the IsaacSim compatible nodes to get rendering support.

Allocate gpu: `salloc --gres=gpu:1 --mem=5GB --cpus-per-task=4 --constrain=isengard`

## Nodes

| Node | GPUs | Constraint |
|---|---|---|
| arwen | 10× RTX 3080 | `--constrain=arwen` |
| isengard | 2× RTX 3080 | `--constrain=isengard` |
| belegost | 10× RTX 2080 Ti | `--constrain=belegost` |

These three have Ubuntu 22.04, Apptainer, and host NVIDIA Vulkan (libGLX_nvidia.so). nvidia-smi inside apptainer --nv is not enough; use the launchers below.

## Carla setup
tbd

## Bench2Drive Repo Setup

1. Create venv: `conda create -n b2d_zoo.venv python=3.8`
2. Activate: `conda activate b2d_zoo.venv`
3. Setup GCC 11 and its paths:
    * Install: `mamba install -c conda-forge -c nvidia/label/cuda-11.8.0 'gcc_linux-64=11' 'gxx_linux-64=11'`
    * Locate and verify its compiler: `which gcc && which g++ && gcc --version && g++ --version`
    * Set CC and CXX to those paths before building: `export CC=/usr/bin/gcc && export CXX=/usr/bin/g++`
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
    * `export CUDA_HOME="$CONDA_PREFIX"`
    * `export PATH="$CUDA_HOME/bin:$PATH"`
    * `export TORCH_CUDA_ARCH_LIST="7.5"`
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
* tbd