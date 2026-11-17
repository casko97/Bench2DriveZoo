# Install Details

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
* `export CARLA_ROOT=YOUR_CARLA_PATH`
* Important!!! Otherwise, the python environment can not find carla package
`echo "$CARLA_ROOT/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg" >> YOUR_CONDA_PATH/envs/YOUR_CONDA_ENV_NAME/lib/python3.8/site-packages/carla.pth` # python 3.8 also works well, please set YOUR_CONDA_PATH and YOUR_CONDA_ENV_NAME

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
* Prepare dataset: `cd mmcv/datasets && python prepare_B2D_mini.py --workers 4` (see [repo](https://github.com/Thinklab-SJTU/Bench2DriveZoo/blob/uniad/vad/docs/DATA_PREP.md))

#### v0.0.4
* Download v0.0.4: `hf download rethinklab/Bench2Drive-V0.0.4 --repo-type dataset --local-dir Bench2Drive-V0.0.4`
* Once the intended archive set has downloaded, create a deterministic 80/10/10 route split: `cd mmcv/datasets && python prepare_B2Dv004.py --write-split-only`.
  This writes `data/splits/bench2drive_v0.0.4_train_val_test_split.json`, using seed `20261117`.
* Extract the route archives and prepare their info files: `cd mmcv/datasets && python prepare_B2Dv004.py --extract --workers 4`.
  Extracted routes are placed in `data/bench2drive/v0.0.4`; generated info files are written to `data/infos/v0.0.4`.
* The preparer reuses an existing manifest to keep the split stable. Use `--regenerate-split` only when deliberately replacing it, for example after completing a partial download.

## Open-loop eval

Run openloop eval: `./adzoo/vad/dist_test.sh ./adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py ./ckpts/vad_b2d_base/vad_b2d_base.pth 1`

## Closed-loop eval

[Instructions here](https://github.com/Thinklab-SJTU/Bench2DriveZoo/blob/uniad/vad/docs/EVAL_IN_CARLA.md)

