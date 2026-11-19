# Install Details
Make sure that Bench2Drive are checked out at 'origin/0.0.4', and that becnh2DriveZoo are based on 'uniad/vad-0.0.4'.

## Carla setup
tbd

## Bench2Drive Repo Setup

1. Create venv: `conda create -n b2d_zoo python=3.8`
2. Activate: `conda activate b2d_zoo`
3. CUDA and torch: Update the environment: `mamba env update -n b2d_zoo -f conda.yaml`
4. To find the cluster’s compiler, first check whether GCC 11 is at the paths in the existing setup notes: `ls -l /usr/bin/gcc-11 /usr/bin/g++-11`
    * If they exist, verify them: `/usr/bin/gcc-11 --version && /usr/bin/g++-11 --version`
    * Otherwise, check whether the cluster uses environment modules: `module avail gcc && module avail cuda`
    * After loading the appropriate GCC module, locate and verify its compiler: `which gcc && which g++ && gcc --version && g++ --version`
    * Set CC and CXX to those paths before building: `export CC=/path/to/gcc && export CXX=/path/to/g++`
5. To identify the GPU and its compute capability: `nvidia-smi && python -c 'import torch; print(torch.cuda.get_device_name(0)); print(torch.cuda.get_device_capability(0))'`
    * PyTorch prints the capability as a pair, such as *(8, 0)*. Set `TORCH_CUDA_ARCH_LIST`, convert that to *8.0*
6. Rebuild the projects CUDA extensions after installing dependencies (with allocated gpu):
    * Allocate gpu: `salloc --gres=gpu:1 --mem=5GB --cpus-per-task=4`
    * Run:
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