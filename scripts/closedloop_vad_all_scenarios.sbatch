#!/usr/bin/env bash
#SBATCH --job-name=vad-closed-all
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:2
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --time=24:00:00
#SBATCH --constraint=arwen
#SBATCH --output=vad-closed-all-%j.out
#SBATCH --error=vad-closed-all-%j.err

# Submit from the Bench2DriveZoo repository root. The common launcher activates
# Conda, checks the allocated GPUs and writes the run log and artifacts.
set -euo pipefail
export CLOSED_LOOP_SCENARIOS=all
exec bash "${SLURM_SUBMIT_DIR:-$PWD}/scripts/closedloop_vad_one_scenario.sbatch"
