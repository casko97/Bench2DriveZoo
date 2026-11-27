
import argparse
import json
import re
from pathlib import Path
from collections import Counter, defaultdict

import numpy as np
from scipy.signal import savgol_filter


# ============================================================
# BENCH2DRIVE COMFORT THRESHOLDS
# ============================================================

max_abs_mag_jerk = 8.37
max_abs_lat_accel = 4.89
max_lon_accel = 2.40
min_lon_accel = -4.05
max_abs_yaw_accel = 1.93
max_abs_lon_jerk = 4.13
max_abs_yaw_rate = 0.95

METRIC_KEYS = (
    "acceleration",
    "angular_velocity",
    "forward_vector",
    "right_vector",
    "location",
    "rotation",
)


# ============================================================
# ORIGINAL COMFORT METRIC HELPERS
# ============================================================

def chunk_array(arr, m):
    return [
        arr[i:i + m]
        for i in range(0, len(arr), m)
    ]


def chunk_arrays(arrays, m):
    return [chunk_array(arr, m) for arr in arrays]


def _within_bound(metric, min_bound=None, max_bound=None):
    if min_bound is None:
        min_bound = -np.inf
    if max_bound is None:
        max_bound = np.inf

    values = np.asarray(metric)

    return np.all(
        (values > min_bound) &
        (values < max_bound),
        axis=-1
    )


def _phase_unwrap(headings):
    two_pi = 2.0 * np.pi
    adjustments = np.zeros_like(headings)

    adjustments[..., 1:] = np.cumsum(
        np.round(
            np.diff(headings, axis=-1) / two_pi
        ),
        axis=-1
    )

    return headings - two_pi * adjustments


# ============================================================
# COMFORT CALCULATION
# ============================================================

def compute_comfort_metric(
    acceleration,
    angular_velocity,
    forward_vector,
    right_vector,
    location,
    rotation,
    window_size=7,
    poly_order=2,
    deriv_order=1,
    time_interval=0.1
):
    window_size = min(window_size, len(acceleration))

    if poly_order >= window_size:
        raise ValueError(
            "Trajectory too short for Savitzky-Golay filter"
        )

    acc = np.asarray(acceleration)
    angular = np.asarray(angular_velocity)
    forward = np.asarray(forward_vector)
    right = np.asarray(right_vector)

    acc_2d = acc[:, :2]
    forward_2d = forward[:, :2]
    right_2d = right[:, :2]

    yaw_rate = _phase_unwrap(angular[:, 2])

    lon_acc = np.einsum(
        "ij,ij->i",
        acc_2d,
        forward_2d
    )

    lat_acc = np.einsum(
        "ij,ij->i",
        acc_2d,
        right_2d
    )

    magnitude_acc = np.hypot(
        acc_2d[:, 0],
        acc_2d[:, 1]
    )

    # Preserve original implementation.
    yaw_acc = savgol_filter(
        yaw_rate,
        polyorder=poly_order,
        window_length=window_size
    )

    yaw_rate = savgol_filter(
        yaw_rate,
        polyorder=poly_order,
        window_length=window_size
    )

    lon_acc = savgol_filter(
        lon_acc,
        polyorder=poly_order,
        window_length=window_size
    )

    lat_acc = savgol_filter(
        lat_acc,
        polyorder=poly_order,
        window_length=window_size
    )

    magnitude_acc = savgol_filter(
        magnitude_acc,
        polyorder=poly_order,
        window_length=window_size
    )

    magnitude_jerk = savgol_filter(
        magnitude_acc,
        polyorder=poly_order,
        window_length=window_size,
        deriv=deriv_order,
        delta=time_interval
    )

    lon_jerk = savgol_filter(
        lon_acc,
        polyorder=poly_order,
        window_length=window_size,
        deriv=deriv_order,
        delta=time_interval
    )

    results = [
        _within_bound(
            lon_acc,
            min_lon_accel,
            max_lon_accel
        ),
        _within_bound(
            lat_acc,
            -max_abs_lat_accel,
            max_abs_lat_accel
        ),
        _within_bound(
            magnitude_jerk,
            -max_abs_mag_jerk,
            max_abs_mag_jerk
        ),
        _within_bound(
            lon_jerk,
            -max_abs_lon_jerk,
            max_abs_lon_jerk
        ),
        _within_bound(
            yaw_acc,
            -max_abs_yaw_accel,
            max_abs_yaw_accel
        ),
        _within_bound(
            yaw_rate,
            -max_abs_yaw_rate,
            max_abs_yaw_rate
        )
    ]

    return bool(np.all(results))


def seg_compute_comfort_metric(
    acceleration,
    angular_velocity,
    forward_vector,
    right_vector,
    location,
    rotation,
    per_step=20
):
    arrays = [
        acceleration,
        angular_velocity,
        forward_vector,
        right_vector,
        location,
        rotation
    ]

    episode_len = len(angular_velocity)

    if episode_len < 3:
        raise ValueError(
            "Trajectory contains fewer than 3 samples"
        )

    if episode_len <= per_step:
        return float(
            compute_comfort_metric(*arrays)
        )

    segments = chunk_arrays(arrays, per_step)
    results = []

    for i in range(len(segments[0])):
        if len(segments[0][i]) < per_step:
            continue

        segment = [
            segments[j][i]
            for j in range(len(segments))
        ]

        results.append(
            compute_comfort_metric(*segment)
        )

    if not results:
        raise ValueError("No valid trajectory segments")

    return results.count(True) / len(results)


# ============================================================
# RECURSIVE BATCH METRIC LOOKUP
# ============================================================

def build_metric_lookup(metric_dir):
    """
    Search the actual Bench2DriveZoo batch structure:

    batch_*/attempt_*/routes_*/metric_info.json

    JSON save_name:
        RouteScenario_9646_rep0_...

    Folder name:
        routes_RouteScenario_9646_rep0_...

    Only remove the optional routes_ prefix.
    """

    metric_root = Path(metric_dir)

    if not metric_root.is_dir():
        raise NotADirectoryError(
            f"Metric root does not exist: {metric_root}"
        )

    metric_files = sorted(
        metric_root.glob(
            "batch_*/attempt_*/routes_*/metric_info.json"
        )
    )

    lookup = defaultdict(list)

    for metric_file in metric_files:
        folder_name = metric_file.parent.name

        if folder_name.startswith("routes_"):
            folder_name = folder_name[len("routes_"):]

        lookup[folder_name].append(metric_file)

    print("\n========== METRIC DISCOVERY ==========")
    print(f"Metric root:        {metric_root}")
    print(f"Metric files found: {len(metric_files)}")
    print(f"Unique names:       {len(lookup)}")
    print("======================================")

    return lookup, metric_files


# ============================================================
# LOAD TELEMETRY
# ============================================================

def load_metric_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    if not isinstance(json_data, dict) or not json_data:
        raise ValueError(
            "Metric file is empty or invalid"
        )

    result = {
        key: []
        for key in METRIC_KEYS
    }

    for timestamp, sample in json_data.items():
        if not isinstance(sample, dict):
            raise ValueError(
                f"Invalid sample at {timestamp}"
            )

        for key in METRIC_KEYS:
            if key not in sample:
                raise ValueError(
                    f"Missing '{key}' at {timestamp}"
                )

            result[key].append(sample[key])

    for key in METRIC_KEYS:
        result[key] = np.asarray(
            result[key],
            dtype=float
        )

        if not np.all(np.isfinite(result[key])):
            raise ValueError(
                f"Non-finite telemetry in {key}"
            )

    return result


# ============================================================
# DRIVING EFFICIENCY
# ============================================================

def compute_driving_efficiency(record):
    infractions = record.get(
        "infractions", {}
    ).get("min_speed_infractions", [])

    percentages = []

    for infraction in infractions:
        match = re.search(
            r"\b\d+\.?\d*%",
            str(infraction)
        )

        if match is None:
            continue

        value = float(
            match.group().rstrip("%")
        )

        if value > 1000:
            continue

        percentages.append(value)

    if not percentages:
        return None

    return sum(percentages) / len(percentages)


# ============================================================
# MAIN
# ============================================================

def main(args):
    result_file = Path(args.file).resolve()
    metric_root = Path(args.metric_dir).resolve()

    if not result_file.is_file():
        raise FileNotFoundError(result_file)

    if not metric_root.is_dir():
        raise NotADirectoryError(metric_root)

    with open(result_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data["_checkpoint"]["records"]

    if not isinstance(records, list):
        raise ValueError(
            "_checkpoint.records must be a list"
        )

    expected_routes = len(records)

    print("\n" + "=" * 60)
    print("BENCH2DRIVE EFFICIENCY & SMOOTHNESS")
    print("=" * 60)
    print(f"Evaluation records: {expected_routes}")

    # --------------------------------------------------------
    # Discover metric files
    # --------------------------------------------------------

    lookup, metric_files = build_metric_lookup(
        metric_root
    )

    # --------------------------------------------------------
    # Match records to files
    # --------------------------------------------------------

    matched = []
    missing = []
    ambiguous = []
    invalid_names = []
    save_names = []

    for record in records:
        route_id = record.get("route_id")
        save_name = record.get("save_name")

        if (
            not isinstance(save_name, str)
            or not save_name
            or Path(save_name).name != save_name
            or save_name in (".", "..")
        ):
            invalid_names.append({
                "route_id": route_id,
                "save_name": save_name
            })
            continue

        save_names.append(save_name)
        paths = lookup.get(save_name, [])

        if len(paths) == 0:
            missing.append({
                "route_id": route_id,
                "save_name": save_name
            })

        elif len(paths) > 1:
            ambiguous.append({
                "route_id": route_id,
                "save_name": save_name,
                "paths": [str(p) for p in paths]
            })

        else:
            matched.append((record, paths[0]))

    duplicate_records = {
        name: count
        for name, count in Counter(save_names).items()
        if count > 1
    }

    matched = [
        (record, path)
        for record, path in matched
        if record["save_name"] not in duplicate_records
    ]

    # --------------------------------------------------------
    # Diagnostics
    # --------------------------------------------------------

    print("\n========== METRIC MATCHING ==========")
    print(f"Expected records:       {expected_routes}")
    print(f"Metric files found:     {len(metric_files)}")
    print(f"Matched records:        {len(matched)}")
    print(f"Missing files:          {len(missing)}")
    print(f"Ambiguous matches:      {len(ambiguous)}")
    print(f"Duplicate record names: {len(duplicate_records)}")
    print(f"Invalid save names:     {len(invalid_names)}")

    if missing:
        print("\nMissing metric files (first 20):")
        for item in missing[:20]:
            print(
                f"  {item['route_id']}: "
                f"{item['save_name']}"
            )

    if ambiguous:
        print("\nAmbiguous metric files (first 20):")
        for item in ambiguous[:20]:
            print(f"  {item['route_id']}:")
            for path in item["paths"]:
                print(f"    {path}")

    if duplicate_records:
        print("\nDuplicate record names:")
        for name, count in duplicate_records.items():
            print(f"  {name}: {count}")

    print("=====================================\n")

    matching_complete = (
        len(matched) == expected_routes
        and not missing
        and not ambiguous
        and not duplicate_records
        and not invalid_names
    )

    if not matching_complete and not args.allow_partial:
        raise SystemExit(
            "ERROR: Incomplete or ambiguous metric matching.\n"
            "Use --allow-partial for diagnostic calculations."
        )

    # --------------------------------------------------------
    # Compute smoothness
    # --------------------------------------------------------

    comfort_results = []
    telemetry_errors = []
    route_results = []

    print("Processing route telemetry...")

    for index, (record, metric_path) in enumerate(
        matched, 1
    ):
        route_id = record.get("route_id")

        try:
            telemetry = load_metric_file(
                metric_path
            )

            comfort = seg_compute_comfort_metric(
                **telemetry
            )

            comfort_results.append(comfort)

            route_results.append({
                "route_id": route_id,
                "save_name": record["save_name"],
                "metric_file": str(metric_path),
                "smoothness": comfort,
                "samples": len(
                    telemetry["acceleration"]
                )
            })

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            IndexError
        ) as exc:
            telemetry_errors.append({
                "route_id": route_id,
                "metric_file": str(metric_path),
                "error": str(exc)
            })

            print(
                f"WARNING: Route {route_id}: {exc}"
            )

        if index % 25 == 0 or index == len(matched):
            print(
                f"Processed {index}/{len(matched)} routes"
            )

    # --------------------------------------------------------
    # Compute efficiency
    # --------------------------------------------------------

    efficiency_results = []
    efficiency_missing = []

    for record in records:
        efficiency = compute_driving_efficiency(
            record
        )

        if efficiency is None:
            efficiency_missing.append(
                record.get("route_id")
            )
        else:
            efficiency_results.append(efficiency)

    # --------------------------------------------------------
    # Aggregate
    # --------------------------------------------------------

    driving_efficiency = (
        sum(efficiency_results) /
        len(efficiency_results)
        if efficiency_results
        else None
    )

    driving_smoothness = (
        sum(comfort_results) /
        len(comfort_results)
        if comfort_results
        else None
    )

    valid_smoothness = (
        matching_complete
        and not telemetry_errors
        and len(comfort_results) == expected_routes
    )

    valid_efficiency = (
        matching_complete
        and len(efficiency_results) > 0
    )

    # --------------------------------------------------------
    # Final results
    # --------------------------------------------------------

    print("\n" + "=" * 60)
    print("FINAL BENCH2DRIVE RESULTS")
    print("=" * 60)

    print(f"Total evaluation routes:  {expected_routes}")
    print(f"Matched metric files:     {len(matched)}")
    print(f"Smoothness routes scored: {len(comfort_results)}")
    print(f"Telemetry errors:         {len(telemetry_errors)}")
    print(f"Efficiency observations:  {len(efficiency_results)}")
    print(f"No efficiency percentage: {len(efficiency_missing)}")

    if driving_efficiency is not None:
        print(
            f"\nDriving Efficiency: "
            f"{driving_efficiency:.4f}"
        )
    else:
        print("\nDriving Efficiency: N/A")

    if driving_smoothness is not None:
        print(
            f"Driving Smoothness: "
            f"{driving_smoothness:.4f}"
        )
    else:
        print("Driving Smoothness: N/A")

    print(f"\nValid smoothness: {valid_smoothness}")
    print(f"Valid efficiency: {valid_efficiency}")

    if not valid_smoothness:
        print(
            "\nWARNING: Smoothness is incomplete. "
            "Reported score is diagnostic only."
        )

    print("=" * 60)

    # --------------------------------------------------------
    # Save JSON
    # --------------------------------------------------------

    output_path = result_file.with_name(
        result_file.stem +
        "_efficiency_smoothness.json"
    )

    output = {
        "evaluation_file": str(result_file),
        "metric_root": str(metric_root),
        "total_routes": expected_routes,
        "metric_files_found": len(metric_files),
        "matched_metric_files": len(matched),
        "smoothness_routes_scored": len(comfort_results),
        "efficiency_observations": len(efficiency_results),
        "driving_efficiency": driving_efficiency,
        "driving_smoothness": driving_smoothness,
        "valid_smoothness": valid_smoothness,
        "valid_efficiency": valid_efficiency,
        "missing_metric_files": missing,
        "ambiguous_metric_files": ambiguous,
        "duplicate_record_names": duplicate_records,
        "invalid_save_names": invalid_names,
        "telemetry_errors": telemetry_errors,
        "routes_without_efficiency": efficiency_missing,
        "route_smoothness": route_results
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    print(f"\nResults saved to: {output_path}")
    print("Finished!")


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Calculate Bench2Drive efficiency and smoothness "
            "from nested batch evaluation folders."
        )
    )

    parser.add_argument(
        "-f",
        "--file",
        required=True,
        help="Path to merged evaluation JSON"
    )

    parser.add_argument(
        "-m",
        "--metric-dir",
        required=True,
        help="Root directory containing batch folders"
    )

    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow diagnostic calculations with missing routes"
    )

    args = parser.parse_args()
    main(args)
