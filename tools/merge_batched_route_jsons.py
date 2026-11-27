
import json
import argparse
from pathlib import Path
from collections import Counter

EXPECTED_ROUTES = 220


def merge_route_json(folder_path, expected_routes=EXPECTED_ROUTES):
    folder = Path(folder_path)

    if not folder.is_dir():
        raise ValueError(f"Folder does not exist: {folder}")

    # Recursively find evaluation JSON files in all batches/attempts.
    # This excludes metric_info.json and other unrelated files.
    file_paths = sorted(folder.rglob("eval_*.json"))

    merged_records = []
    driving_scores = []
    success_num = 0
    processed_files = 0

    print(f"\nSearching for evaluation JSON files in: {folder}")
    print(f"Found {len(file_paths)} candidate JSON files.\n")

    for file_path in file_paths:
        if file_path.name == "merged.json":
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARNING: Cannot read {file_path}: {exc}")
            continue

        checkpoint = data.get("_checkpoint", {})
        records = checkpoint.get("records")

        if not isinstance(records, list):
            print(f"Skipping (no valid records): {file_path}")
            continue

        processed_files += 1

        print(f"Processing: {file_path.relative_to(folder)}")
        print(f"  Routes found: {len(records)}")

        for record in records:
            if not isinstance(record, dict):
                print("  WARNING: Skipping invalid route record")
                continue

            rd = record.copy()
            rd.pop("index", None)

            merged_records.append(rd)

            score = rd.get("scores", {}).get(
                "score_composed", 0
            )
            driving_scores.append(score)

            if rd.get("status") in ("Completed", "Perfect"):
                infractions = rd.get("infractions", {})

                success_flag = True

                for key, value in infractions.items():
                    if key != "min_speed_infractions" and len(value) > 0:
                        success_flag = False
                        break

                if success_flag:
                    success_num += 1

    # --------------------------------------------------
    # Route statistics
    # --------------------------------------------------

    num_routes = len(merged_records)

    route_ids = [
        rd.get("route_id")
        for rd in merged_records
    ]

    counts = Counter(route_ids)

    duplicates = {
        route_id: count
        for route_id, count in counts.items()
        if count > 1
    }

    unique_routes = len(counts)

    # --------------------------------------------------
    # Print evaluation summary
    # --------------------------------------------------

    print("\n" + "=" * 60)
    print("BENCH2DRIVE EVALUATION SUMMARY")
    print("=" * 60)

    print(f"Evaluation JSON files processed: {processed_files}")
    print(f"Total route records found:      {num_routes}")
    print(f"Unique route IDs found:         {unique_routes}")
    print(f"Expected routes:                {expected_routes}")
    print(f"Successful routes:              {success_num}")

    if duplicates:
        print("\nWARNING: Duplicate route IDs detected!")

        for route_id, count in sorted(
            duplicates.items(),
            key=lambda item: str(item[0])
        ):
            print(f"  {route_id}: {count} occurrences")

    if num_routes != expected_routes:
        print(
            f"\nWARNING: Found {num_routes} route records, "
            f"but expected {expected_routes}."
        )
        print(
            "All metrics (Driving Score, Success Rate, Ability) "
            "may be inaccurate!"
        )

    if unique_routes != expected_routes:
        print(
            "\nWARNING: Unique route count does not match "
            "the expected benchmark size."
        )

    if num_routes == 0:
        print("\nNo route records found. No merged file created.")
        return

    # --------------------------------------------------
    # Calculate Bench2Drive metrics
    # --------------------------------------------------

    # Keep the original benchmark denominator.
    driving_score = sum(driving_scores) / expected_routes
    success_rate = success_num / expected_routes

    print("\n" + "-" * 60)
    print("METRICS")
    print("-" * 60)

    print(f"Driving Score: {driving_score:.4f}")
    print(f"Success Rate:  {success_rate:.4f}")
    print(f"Success Rate:  {success_rate * 100:.2f}%")

    # --------------------------------------------------
    # Sort merged records
    # --------------------------------------------------

    merged_records = sorted(
        merged_records,
        key=lambda d: str(d.get("route_id", "")),
        reverse=True
    )

    # --------------------------------------------------
    # Create merged JSON
    # --------------------------------------------------

    merged_data = {
        "_checkpoint": {
            "records": merged_records
        },
        "driving score": driving_score,
        "success rate": success_rate,
        "eval num": num_routes,
        "unique route count": unique_routes,
        "expected route count": expected_routes,
        "duplicate route ids": duplicates,
    }

    output_path = folder / "merged.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(merged_data, file, indent=4)

    print("\n" + "=" * 60)
    print(f"Merged JSON saved to: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Merge Bench2Drive evaluation JSON files "
            "from nested batch and attempt directories."
        )
    )

    parser.add_argument(
        "-f",
        "--folder",
        required=True,
        help="Root evaluation folder containing batch_* directories"
    )

    parser.add_argument(
        "--expected-routes",
        type=int,
        default=EXPECTED_ROUTES,
        help="Expected number of routes (default: 220)"
    )

    args = parser.parse_args()

    if args.expected_routes <= 0:
        parser.error("--expected-routes must be positive")

    merge_route_json(
        args.folder,
        expected_routes=args.expected_routes
    )
