
import argparse
import json
import os
import re
import xml.etree.ElementTree as ET

from collections import Counter, defaultdict
from pathlib import Path

import carla
from agents.navigation.global_route_planner import GlobalRoutePlanner


# ============================================================
# ABILITY DEFINITIONS
# Preserve the original Bench2Drive ability categories.
# ============================================================

ABILITY = {
    "Overtaking": [
        "Accident", "AccidentTwoWays",
        "ConstructionObstacle", "ConstructionObstacleTwoWays",
        "HazardAtSideLaneTwoWays", "HazardAtSideLane",
        "ParkedObstacleTwoWays", "ParkedObstacle",
        "VehicleOpensDoorTwoWays"
    ],
    "Merging": [
        "CrossingBicycleFlow", "EnterActorFlow",
        "HighwayExit", "InterurbanActorFlow",
        "HighwayCutIn", "InterurbanAdvancedActorFlow",
        "MergerIntoSlowTrafficV2", "MergerIntoSlowTraffic",
        "NonSignalizedJunctionLeftTurn",
        "NonSignalizedJunctionRightTurn",
        "NonSignalizedJunctionLeftTurnEnterFlow",
        "ParkingExit", "SequentialLaneChange",
        "SignalizedJunctionLeftTurn",
        "SignalizedJunctionRightTurn",
        "SignalizedJunctionLeftTurnEnterFlow"
    ],
    "Emergency_Brake": [
        "BlockedIntersection", "DynamicObjectCrossing",
        "HardBreakRoute", "OppositeVehicleTakingPriority",
        "OppositeVehicleRunningRedLight", "ParkingCutIn",
        "PedestrianCrossing", "ParkingCrossingPedestrian",
        "StaticCutIn", "VehicleTurningRoute",
        "VehicleTurningRoutePedestrian", "ControlLoss"
    ],
    "Give_Way": [
        "InvadingTurn", "YieldToEmergencyVehicle"
    ],
    "Traffic_Signs": [
        "BlockedIntersection",
        "OppositeVehicleTakingPriority",
        "OppositeVehicleRunningRedLight",
        "PedestrianCrossing", "VehicleTurningRoute",
        "VehicleTurningRoutePedestrian", "EnterActorFlow",
        "CrossingBicycleFlow",
        "NonSignalizedJunctionLeftTurn",
        "NonSignalizedJunctionRightTurn",
        "NonSignalizedJunctionLeftTurnEnterFlow",
        "SignalizedJunctionLeftTurn",
        "SignalizedJunctionRightTurn",
        "SignalizedJunctionLeftTurnEnterFlow",
        "T_Junction", "VanillaNonSignalizedTurn",
        "VanillaSignalizedTurnEncounterGreenLight",
        "VanillaSignalizedTurnEncounterRedLight",
        "VanillaNonSignalizedTurnEncounterStopsign"
    ]
}


# ============================================================
# ROUTE ID NORMALIZATION
# ============================================================

def normalize_route_id(value):
    if value is None:
        return None

    value = str(value).strip()

    match = re.fullmatch(
        r"(?:routes_)?RouteScenario_(\d+)(?:_rep\d+)?",
        value
    )

    if match:
        return str(int(match.group(1)))

    match = re.fullmatch(r"Route_(\d+)", value)

    if match:
        return str(int(match.group(1)))

    if value.isdigit():
        return str(int(value))

    return None


# ============================================================
# LOAD EVALUATION RESULTS
# ============================================================

def load_records(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data["_checkpoint"]["records"]

    if not isinstance(records, list):
        raise ValueError("Invalid _checkpoint.records")

    lookup = defaultdict(list)
    invalid = []

    for record in records:
        if not isinstance(record, dict):
            invalid.append(record)
            continue

        route_id = normalize_route_id(
            record.get("route_id")
        )

        if route_id is None:
            invalid.append(record.get("route_id"))
        else:
            lookup[route_id].append(record)

    return records, lookup, invalid


# ============================================================
# LOAD XML ROUTES
# ============================================================

def load_xml_routes(xml_path):
    tree = ET.parse(xml_path)
    routes = tree.getroot().findall("route")

    return routes


def get_scenario(route):
    scenario = route.find("scenarios/scenario")

    if scenario is None:
        raise ValueError(
            f"Route {route.get('id')} has no scenario"
        )

    scenario_type = scenario.get("type")

    if not scenario_type:
        raise ValueError(
            f"Route {route.get('id')} has no scenario type"
        )

    return scenario_type


# ============================================================
# SUCCESS DEFINITION
# ============================================================

def get_infraction_status(record):
    infractions = record.get("infractions", {})

    for name, value in infractions.items():
        if name == "min_speed_infractions":
            continue

        if value:
            return True

    return False


def is_successful(record):
    return (
        record.get("status") in ("Completed", "Perfect")
        and not get_infraction_status(record)
    )


# ============================================================
# OFFLINE CARLA MAP HELPERS
# ============================================================

def load_offline_map(town_name, map_root):
    candidates = [
        map_root / "OpenDrive" / f"{town_name}.xodr",
        map_root / town_name / "OpenDrive" / f"{town_name}.xodr"
    ]

    for path in candidates:
        if path.exists():
            with open(path, "r") as f:
                xodr = f.read()

            return carla.Map(town_name, xodr)

    raise FileNotFoundError(
        f"OpenDrive file not found for {town_name}"
    )


def get_position(xml_route):
    positions = xml_route.findall("waypoints/position")

    return [
        carla.Location(
            float(pos.get("x")),
            float(pos.get("y")),
            float(pos.get("z"))
        )
        for pos in positions
    ]


def get_waypoint_route(locs, grp):
    route = []

    for i in range(len(locs) - 1):
        trace = grp.trace_route(
            locs[i],
            locs[i + 1]
        )

        for wp, _ in trace:
            route.append(wp)

    return route


# ============================================================
# TRAFFIC SIGNS SPECIAL HANDLING
# ============================================================

def traffic_sign_success(
    xml_route,
    record,
    grp
):
    """
    Preserve the original Bench2Drive special rule.

    A failed route may still count as Traffic Signs success
    if it passed the first junction without stop/red-light
    infractions.
    """

    locations = get_position(xml_route)

    waypoint_route = get_waypoint_route(
        locations, grp
    )

    if not waypoint_route:
        raise RuntimeError("Empty waypoint route")

    count = 0
    junction_found = False

    for wp in waypoint_route:
        count += 1

        if wp.is_junction:
            junction_found = True
            break

    if not junction_found:
        raise RuntimeError("No junction found in route")

    junction_completion = (
        float(count + 8) / len(waypoint_route)
    )

    record_completion = (
        float(record["scores"]["score_route"]) / 100.0
    )

    infractions = record["infractions"]

    stop_infraction = infractions.get(
        "stop_infraction", []
    )

    red_light_infraction = infractions.get(
        "red_light", []
    )

    return (
        record_completion > junction_completion
        and not stop_infraction
        and not red_light_infraction
    )


# ============================================================
# VALIDATE ROUTES
# ============================================================

def validate_routes(routes, records, lookup, invalid):
    xml_ids = [
        normalize_route_id(r.get("id"))
        for r in routes
    ]

    xml_counts = Counter(xml_ids)

    duplicates_xml = {
        k: v for k, v in xml_counts.items()
        if v > 1
    }

    duplicates_json = {
        k: len(v) for k, v in lookup.items()
        if len(v) > 1
    }

    xml_set = set(xml_ids)
    json_set = set(lookup)

    missing = xml_set - json_set
    extra = json_set - xml_set

    matched = xml_set & json_set

    print("\n========== ROUTE VALIDATION ==========")

    print(f"Routes in XML:        {len(routes)}")
    print(f"Records in JSON:      {len(records)}")
    print(f"Unique XML IDs:       {len(xml_set)}")
    print(f"Unique JSON IDs:      {len(json_set)}")
    print(f"Matching IDs:         {len(matched)}")
    print(f"Missing XML routes:   {len(missing)}")
    print(f"Extra JSON routes:    {len(extra)}")
    print(f"Duplicate XML IDs:    {len(duplicates_xml)}")
    print(f"Duplicate JSON IDs:   {len(duplicates_json)}")
    print(f"Invalid JSON IDs:     {len(invalid)}")

    if missing:
        print("\nMissing routes:")
        for route_id in sorted(missing, key=str)[:20]:
            print(f"  {route_id}")

    if extra:
        print("\nExtra JSON routes:")
        for route_id in sorted(extra, key=str)[:20]:
            print(f"  {route_id}")

    if duplicates_json:
        print("\nDuplicate JSON IDs:")
        for route_id, count in duplicates_json.items():
            print(f"  {route_id}: {count}")

    if invalid:
        print("\nInvalid JSON IDs:")
        for value in invalid[:20]:
            print(f"  {value!r}")

    complete = (
        len(routes) == len(records)
        and len(xml_set) == len(routes)
        and len(json_set) == len(records)
        and xml_set == json_set
        and None not in xml_set
        and not invalid
        and not duplicates_xml
        and not duplicates_json
    )

    print(f"\nComplete evaluation: {complete}")
    print("======================================\n")

    return complete


# ============================================================
# MAIN
# ============================================================

def main(args):
    result_file = Path(args.result_file)
    routes_file = Path(args.file)

    carla_root = Path(
        os.environ.get("CARLA_ROOT", ".")
    )

    map_root = (
        carla_root /
        "CarlaUE4/Content/Carla/Maps"
    )

    print(f"[debug] map_root = {map_root}")

    records, lookup, invalid = load_records(
        result_file
    )

    routes = load_xml_routes(routes_file)

    complete = validate_routes(
        routes, records, lookup, invalid
    )

    if not complete and not args.allow_partial:
        raise SystemExit(
            "ERROR: Route validation failed. "
            "Use --allow-partial for diagnostic metrics."
        )

    # ------------------------------------------------
    # Dynamic denominators
    # ------------------------------------------------

    ability_stats = {
        name: [0, 0]
        for name in ABILITY
    }

    scenario_stats = defaultdict(
        lambda: [0, 0]
    )

    expected_ability_counts = {
        name: 0
        for name in ABILITY
    }

    expected_scenarios = Counter()

    for route in routes:
        scenario = get_scenario(route)
        expected_scenarios[scenario] += 1

        for ability, scenarios in ABILITY.items():
            if scenario in scenarios:
                expected_ability_counts[ability] += 1

    print("\n========== EXPECTED ABILITY ROUTES ==========")

    for ability, count in expected_ability_counts.items():
        print(f"{ability:20s}: {count}")

    print("============================================\n")

    # ------------------------------------------------
    # Evaluation
    # ------------------------------------------------

    current_town = None
    grp = None

    matched_count = 0
    successful_count = 0
    missing_routes = []
    skipped_routes = []
    driving_scores = []

    for route in sorted(
        routes,
        key=lambda r: r.get("town", "")
    ):
        route_id = normalize_route_id(
            route.get("id")
        )

        scenario = get_scenario(route)
        town = route.get("town")

        matches = lookup.get(route_id, [])

        if len(matches) != 1:
            missing_routes.append(
                [scenario, route_id]
            )
            continue

        record = matches[0]
        matched_count += 1

        successful = is_successful(record)

        if successful:
            successful_count += 1

        driving_scores.append(
            float(record["scores"]["score_composed"])
        )

        scenario_stats[scenario][1] += 1

        if successful:
            scenario_stats[scenario][0] += 1

        for ability, scenarios in ABILITY.items():
            if scenario in scenarios:
                ability_stats[ability][1] += 1

                if successful:
                    ability_stats[ability][0] += 1

        # --------------------------------------------
        # Traffic Signs special rule
        # --------------------------------------------

        if (
            scenario in ABILITY["Traffic_Signs"]
            and not successful
        ):
            try:
                if town != current_town:
                    current_town = town

                    carla_map = load_offline_map(
                        town, map_root
                    )

                    grp = GlobalRoutePlanner(
                        carla_map, 1.0
                    )

                if traffic_sign_success(
                    route, record, grp
                ):
                    ability_stats["Traffic_Signs"][0] += 1

            except Exception as exc:
                skipped_routes.append({
                    "route_id": route_id,
                    "scenario": scenario,
                    "reason": str(exc)
                })

                print(
                    f"WARNING: Traffic Signs evaluation "
                    f"failed for route {route_id}: {exc}"
                )

    # ------------------------------------------------
    # Calculate ability scores
    # ------------------------------------------------

    ability_results = {}
    valid_scores = []

    print("\n========== ABILITY STATISTICS ==========")

    for ability, values in ability_stats.items():
        success_count, route_count = values
        expected_count = expected_ability_counts[ability]

        score = (
            success_count / route_count
            if route_count > 0
            else None
        )

        ability_results[ability] = score

        if score is not None:
            valid_scores.append(score)

        score_text = (
            f"{score * 100:.2f}%"
            if score is not None
            else "N/A"
        )

        print(
            f"{ability:20s} "
            f"success={success_count:3d} "
            f"evaluated={route_count:3d} "
            f"expected={expected_count:3d} "
            f"score={score_text}"
        )

    mean_ability = (
        sum(valid_scores) / len(valid_scores)
        if valid_scores
        else None
    )

    print("========================================\n")

    # ------------------------------------------------
    # Driving Score and Success Rate
    # ------------------------------------------------

    expected_routes = len(routes)

    driving_score = (
        sum(driving_scores) / expected_routes
        if expected_routes > 0
        else None
    )

    success_rate = (
        successful_count / expected_routes
        if expected_routes > 0
        else None
    )

    # Also report observed-route average.
    observed_driving_score = (
        sum(driving_scores) / matched_count
        if matched_count > 0
        else None
    )

    # A missing Traffic Signs calculation must not
    # silently produce a final benchmark score.
    valid_ability_metrics = (
        complete
        and not skipped_routes
        and all(
            value is not None
            for value in ability_results.values()
        )
    )

    # ------------------------------------------------
    # Print final summary
    # ------------------------------------------------

    print("\n========== FINAL RESULTS ==========")

    print(f"Expected routes:    {expected_routes}")
    print(f"Matched routes:     {matched_count}")
    print(f"Successful routes:  {successful_count}")

    if driving_score is not None:
        print(f"Driving Score:      {driving_score:.4f}")

    if success_rate is not None:
        print(
            f"Success Rate:       "
            f"{success_rate * 100:.2f}%"
        )

    if observed_driving_score is not None:
        print(
            f"Observed-route DS:  "
            f"{observed_driving_score:.4f}"
        )

    if mean_ability is not None:
        print(
            f"Mean Ability:       "
            f"{mean_ability * 100:.2f}%"
        )

    print(f"Complete routes:    {complete}")
    print(f"Valid ability:      {valid_ability_metrics}")
    print(f"Traffic sign errors:{len(skipped_routes)}")

    if not valid_ability_metrics:
        print(
            "\nWARNING: Ability results are diagnostic "
            "only and should not be reported as "
            "complete benchmark metrics."
        )

    print("===================================\n")

    # ------------------------------------------------
    # Save results
    # ------------------------------------------------

    output_file = result_file.with_name(
        result_file.stem + "_ability_zoo.json"
    )

    output = {
        "route_configuration": str(routes_file),
        "expected_routes": expected_routes,
        "matched_routes": matched_count,
        "successful_routes": successful_count,
        "complete_route_matching": complete,
        "valid_ability_metrics": valid_ability_metrics,
        "driving_score": driving_score,
        "observed_driving_score": observed_driving_score,
        "success_rate": success_rate,
        "ability": ability_results,
        "mean_ability": mean_ability,
        "ability_statistics": {
            name: {
                "success_count": values[0],
                "evaluated_count": values[1],
                "expected_count": expected_ability_counts[name]
            }
            for name, values in ability_stats.items()
        },
        "scenario_statistics": {
            name: {
                "success_count": values[0],
                "evaluated_count": values[1],
                "expected_count": expected_scenarios[name]
            }
            for name, values in scenario_stats.items()
        },
        "missing_routes": missing_routes,
        "traffic_sign_errors": skipped_routes
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    print(f"Results saved to: {output_file}")


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Bench2DriveZoo ability benchmark "
            "with dynamic route counts."
        )
    )

    parser.add_argument(
        "-f",
        "--file",
        default=(
            "leaderboard/data/"
            "bench2drive_0.0.4_val.xml"
        ),
        help="Route XML used during evaluation"
    )

    parser.add_argument(
        "-r",
        "--result-file",
        required=True,
        help="Path to merged evaluation JSON"
    )

    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow incomplete evaluation for diagnostics"
    )

    args = parser.parse_args()

    main(args)
