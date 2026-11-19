# Install Details
Make sure that Bench2Drive are checked out at 'origin/0.0.4', and that becnh2DriveZoo are based on 'uniad/vad-0.0.4'.

We use the IsaacSim compatible nodes to get rendering support.

## Nodes

| Node | GPUs | Constraint |
|---|---|---|
| arwen | 10× RTX 3080 | `--constraint=arwen` |
| isengard | 2× RTX 3080 | `--constraint=isengard` |
| belegost | 10× RTX 2080 Ti | `--constraint=belegost` |

These three have Ubuntu 22.04, Apptainer, and host NVIDIA Vulkan (libGLX_nvidia.so). nvidia-smi inside apptainer --nv is not enough; use the launchers below.

## Carla setup
tbd

## Bench2Drive Repo Setup

1. Create venv: `conda create -n b2d_zoo.venv python=3.8`
2. Activate: `conda activate b2d_zoo.venv`
3. Select a CUDA 11.8 compatible GCC and G++ compiler on the GPU node:
    * Locate and verify its compiler: `which gcc && which g++ && gcc --version && g++ --version`
    * Set CC and CXX to those paths before building: `export CC=/path/to/gcc && export CXX=/path/to/g++`
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
    ```
    python -m pip install \
    torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 \
    --index-url https://download.pytorch.org/whl/cu118
    ```
6. Install more dependencies
    * Numerical packages: `python -m pip install --only-binary=:all: numpy==1.20.0 scipy==1.10.1 numba==0.48.0 llvmlite==0.31.0`
    * Build tools: `python -m pip install setuptools==75.3.4 wheel==0.45.1 ninja==1.13.2 packaging==26.2`
    * The rest: `python -m pip install -r requirements_midgard.txt "numpy==1.20.0"`

* Before proceeding to the following step, allocate gpu: `salloc --gres=gpu:1 --mem=5GB --cpus-per-task=4 --constraint=isengard`
* To identify the GPU and its compute capability (with allocated gpu): `nvidia-smi && python -c 'import torch; print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_capability(0))'`
    * PyTorch prints the capability as a pair, such as *(8, 0)*. Set `TORCH_CUDA_ARCH_LIST`, convert that to *8.0*
* Rebuild the projects CUDA extensions after installing dependencies (with allocated gpu):
    ```
    python -c "import torch; print(torch.cuda.is_available())"
    nvcc --version

    export CUDA_HOME="$CONDA_PREFIX"
    export PATH="$CUDA_HOME/bin:$PATH"
    export MAX_JOBS=4

    pip install -v --no-build-isolation --no-deps -e .
    ```

Make sure the environment knows where Carla is: 
* tbd