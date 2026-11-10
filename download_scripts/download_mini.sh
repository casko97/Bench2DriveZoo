#!/bin/bash

download_dir="Bench2Drive-mini"
repo="rethinklab/Bench2Drive"
files=(
  "HardBreakRoute_Town01_Route30_Weather3.tar.gz"
  "DynamicObjectCrossing_Town02_Route13_Weather6.tar.gz"
  "Accident_Town03_Route156_Weather0.tar.gz"
  "YieldToEmergencyVehicle_Town04_Route165_Weather7.tar.gz"
  "ConstructionObstacle_Town05_Route68_Weather8.tar.gz"
  "ParkedObstacle_Town10HD_Route371_Weather7.tar.gz"
  "ControlLoss_Town11_Route401_Weather11.tar.gz"
  "AccidentTwoWays_Town12_Route1444_Weather0.tar.gz"
  "OppositeVehicleTakingPriority_Town13_Route600_Weather2.tar.gz"
  "VehicleTurningRoute_Town15_Route443_Weather1.tar.gz"
)

echo "Preparing to download the Bench2Drive mini dataset."
echo "Repository: ${repo}"
echo "Destination: ${download_dir}"
echo "Files: ${#files[@]}"

# Check if huggingface-hub is installed.
if ! python -m pip show huggingface-hub > /dev/null 2>&1; then
  echo "huggingface-hub is not installed; installing it now..."
  python -m pip install huggingface-hub
else
  echo "huggingface-hub is already installed."
fi

mkdir -p "${download_dir}"

for index in "${!files[@]}"; do
  file="${files[$index]}"
  echo
  echo "[$((index + 1))/${#files[@]}] Downloading ${file}..."
  hf download \
    --repo-type dataset \
    "${repo}" \
    "${file}" \
    --local-dir "${download_dir}"
  echo "[$((index + 1))/${#files[@]}] Finished ${file}."
done

echo
echo "Bench2Drive mini download complete: ${download_dir}"
