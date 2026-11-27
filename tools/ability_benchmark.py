
import json
import carla
import argparse
import xml.etree.ElementTree as ET
from agents.navigation.global_route_planner import GlobalRoutePlanner
import os
import re
from pathlib import Path
from collections import Counter, defaultdict


EXPECTED_ROUTES = 220


Ability = {
    "Overtaking": [
        'Accident', 'AccidentTwoWays',
        'ConstructionObstacle', 'ConstructionObstacleTwoWays',
        'HazardAtSideLaneTwoWays', 'HazardAtSideLane',
        'ParkedObstacleTwoWays', 'ParkedObstacle',
        'VehicleOpensDoorTwoWays'
    ],
    "Merging": [
        'CrossingBicycleFlow', 'EnterActorFlow',
        'HighwayExit', 'InterurbanActorFlow',
        'HighwayCutIn', 'InterurbanAdvancedActorFlow',
        'MergerIntoSlowTrafficV2', 'MergerIntoSlowTraffic',
        'NonSignalizedJunctionLeftTurn',
        'NonSignalizedJunctionRightTurn',
        'NonSignalizedJunctionLeftTurnEnterFlow',
        'ParkingExit', 'SequentialLaneChange',
        'SignalizedJunctionLeftTurn',
        'SignalizedJunctionRightTurn',
        'SignalizedJunctionLeftTurnEnterFlow'
    ],
    "Emergency_Brake": [
        'BlockedIntersection', 'DynamicObjectCrossing',
        'HardBreakRoute', 'OppositeVehicleTakingPriority',
        'OppositeVehicleRunningRedLight',
        'ParkingCutIn', 'PedestrianCrossing',
        'ParkingCrossingPedestrian', 'StaticCutIn',
        'VehicleTurningRoute',
        'VehicleTurningRoutePedestrian',
        'ControlLoss'
    ],
    "Give_Way": [
        'InvadingTurn', 'YieldToEmergencyVehicle'
    ],
    "Traffic_Signs": [
        'BlockedIntersection',
        'OppositeVehicleTakingPriority',
        'OppositeVehicleRunningRedLight',
        'PedestrianCrossing',
        'VehicleTurningRoute',
        'VehicleTurningRoutePedestrian',
        'EnterActorFlow',
        'CrossingBicycleFlow',
        'NonSignalizedJunctionLeftTurn',
        'NonSignalizedJunctionRightTurn',
        'NonSignalizedJunctionLeftTurnEnterFlow',
        'SignalizedJunctionLeftTurn',
        'SignalizedJunctionRightTurn',
        'SignalizedJunctionLeftTurnEnterFlow',
        'T_Junction',
        'VanillaNonSignalizedTurn',
        'VanillaSignalizedTurnEncounterGreenLight',
        'VanillaSignalizedTurnEncounterRedLight',
        'VanillaNonSignalizedTurnEncounterStopsign'
    ]
}


# =====================================================
# ROUTE ID NORMALIZATION
# =====================================================

def normalize_route_id(route_id):
    """
    Extract the global numeric route ID.

    Supported examples:
      RouteScenario_24211
      routes_RouteScenario_24211
      routes_RouteScenario_24211_rep0
      Route_24211
      24211

    Unknown formats return None rather than guessing.
    """

    if route_id is None:
        return None

    route_id = str(route_id).strip()

    match = re.search(
        r"(?:^|_)RouteScenario_(\d+)(?:_|$)",
        route_id
    )

    if match:
        return str(int(match.group(1)))

    match = re.fullmatch(
        r"Route_(\d+)",
        route_id
    )

    if match:
        return str(int(match.group(1)))

    if route_id.isdigit():
        return str(int(route_id))

    return None


# =====================================================
# INFRACTION AND SUCCESS HANDLING
# =====================================================

def get_infraction_status(record):
    infractions = record.get("infractions", {})

    for infraction, value in infractions.items():
        if infraction == "min_speed_infractions":
            continue

        if value:
            return True

    return False


def update_Ability(scenario_name, statistics, status):
    for ability, scenarios in Ability.items():
        if scenario_name in scenarios:
            statistics[ability][1] += 1

            if status:
                statistics[ability][0] += 1


def update_Success(scenario_name, statistics, status):
    if scenario_name not in statistics:
        statistics[scenario_name] = [0, 0]

    statistics[scenario_name][1] += 1

    if status:
        statistics[scenario_name][0] += 1


# =====================================================
# CARLA ROUTE HELPERS
# =====================================================

def get_position(xml_route):
    waypoints_elem = xml_route.find("waypoints")

    if waypoints_elem is None:
        raise ValueError("Route has no waypoints element")

    keypoints = waypoints_elem.findall("position")

    return [
        carla.Location(
            float(pos.get("x")),
            float(pos.get("y")),
            float(pos.get("z"))
        )
        for pos in keypoints
    ]


def get_waypoint_route(locs, grp):
    route = []

    for i in range(len(locs) - 1):
        interpolated_trace = grp.trace_route(
            locs[i],
            locs[i + 1]
        )

        for wp, _ in interpolated_trace:
            route.append(wp)

    return route


def load_offline_map(town_name, map_root):
    xodr1 = os.path.join(
        map_root,
        "OpenDrive",
        f"{town_name}.xodr"
    )

    xodr2 = os.path.join(
        map_root,
        town_name,
        "OpenDrive",
        f"{town_name}.xodr"
    )

    if os.path.exists(xodr1):
        path = xodr1
    elif os.path.exists(xodr2):
        path = xodr2
    else:
        raise FileNotFoundError(
            f"OpenDrive file not found for {town_name}"
        )

    with open(path, "r") as f:
        xodr = f.read()

    return carla.Map(town_name, xodr)


# =====================================================
# BUILD ROUTE LOOKUP
# =====================================================

def build_route_lookup(records):
    """
    Build lookup from normalized route IDs.

    Duplicate IDs are retained for diagnostics.
    They are not silently overwritten.
    """

    lookup = defaultdict(list)
    invalid = []

    for record in records:
        raw_id = record.get("route_id")
        normalized_id = normalize_route_id(raw_id)

        if normalized_id is None:
            invalid.append(raw_id)
            continue

        lookup[normalized_id].append(record)

    return lookup, invalid


# =====================================================
# ROUTE MATCHING DIAGNOSTICS
# =====================================================

def validate_routes(records, routes):
    lookup, invalid = build_route_lookup(records)

    xml_ids = [
        normalize_route_id(route.get("id"))
        for route in routes
    ]

    xml_counts = Counter(xml_ids)

    duplicate_xml = {
        key: count
        for key, count in xml_counts.items()
        if count > 1
    }

    duplicate_json = {
        key: len(value)
        for key, value in lookup.items()
        if len(value) > 1
    }

    xml_id_set = set(xml_ids)
    json_id_set = set(lookup.keys())

    matched = xml_id_set & json_id_set
    missing = xml_id_set - json_id_set
    extra = json_id_set - xml_id_set

    print("\n" + "=" * 60)
    print("BENCH2DRIVE ROUTE MATCHING DIAGNOSTICS")
    print("=" * 60)

    print(f"Total JSON records:       {len(records)}")
    print(f"Unique normalized IDs:    {len(json_id_set)}")
    print(f"Routes in XML:            {len(routes)}")
    print(f"Matched unique routes:    {len(matched)}")
    print(f"Missing XML routes:       {len(missing)}")
    print(f"Extra JSON routes:        {len(extra)}")
    print(f"Invalid JSON IDs:         {len(invalid)}")
    print(f"Duplicate JSON IDs:       {len(duplicate_json)}")
    print(f"Duplicate XML IDs:        {len(duplicate_xml)}")

    print("\nSample original JSON route IDs:")

    for record in records[:10]:
        raw = record.get("route_id")
        normalized = normalize_route_id(raw)

        print(f"  {raw!r} -> {normalized!r}")

    if missing:
        print("\nMissing XML route IDs (first 20):")
        for route_id in sorted(missing, key=str)[:20]:
            print(f"  {route_id}")

    if extra:
        print("\nExtra JSON route IDs (first 20):")
        for route_id in sorted(extra, key=str)[:20]:
            print(f"  {route_id}")

    if duplicate_json:
        print("\nDuplicate JSON route IDs:")
        for route_id, count in sorted(
            duplicate_json.items(),
            key=lambda x: str(x[0])
        ):
            print(f"  {route_id}: {count} records")

    if invalid:
        print("\nUnrecognized route ID formats:")
        for raw_id in invalid[:20]:
            print(f"  {raw_id!r}")

    print("=" * 60)

    complete = (
        len(records) == len(routes)
        and len(matched) == len(routes)
        and not missing
        and not extra
        and not invalid
        and not duplicate_json
        and not duplicate_xml
        and None not in xml_id_set
    )

    return lookup, complete


# =====================================================
# MAIN BENCHMARK
# =====================================================

def main(args):
    routes_file = Path(args.file)
    result_file = Path(args.result_file)

    map_root = os.path.join(
        os.environ.get("CARLA_ROOT", "."),
        "CarlaUE4/Content/Carla/Maps"
    )

    print(f"[debug] map_root = {map_root}")

    with open(result_file, "r") as f:
        data = json.load(f)

    records = data["_checkpoint"]["records"]

    tree = ET.parse(routes_file)
    root = tree.getroot()

    routes = sorted(
        root.findall("route"),
        key=lambda x: x.get("town", "")
    )

    # -------------------------------------------------
    # Validate route matching BEFORE metric calculation
    # -------------------------------------------------

    lookup, complete = validate_routes(
        records,
        routes
    )

    if len(routes) != EXPECTED_ROUTES:
        print(
            f"\nWARNING: XML contains {len(routes)} routes, "
            f"expected {EXPECTED_ROUTES}."
        )
        complete = False

    if not complete:
        print(
            "\nWARNING: Route matching is incomplete "
            "or ambiguous."
        )
        print(
            "Ability scores from this input cannot "
            "be treated as official benchmark metrics."
        )

        if not args.allow_partial:
            print(
                "\nStopping before metric calculation."
            )
            print(
                "Inspect the route IDs above, or use "
                "--allow-partial for diagnostic scores."
            )
            return

    # -------------------------------------------------
    # Initialize statistics
    # -------------------------------------------------

    Ability_Statistic = {
        ability: [0, 0]
        for ability in Ability
    }

    Success_Statistic = {}
    crash_route_list = []

    current_town = None
    grp = None
    matched_routes = 0

    # -------------------------------------------------
    # Evaluate routes
    # -------------------------------------------------

    for route in routes:
        scenario_elem = route.find(
            "scenarios/scenario"
        )

        if scenario_elem is None:
            print(
                f"WARNING: Route {route.get('id')} "
                "has no scenario."
            )
            continue

        scenario_name = scenario_elem.get("type")
        route_id = normalize_route_id(
            route.get("id")
        )
        town_name = route.get("town")

        matching_records = lookup.get(
            route_id, []
        )

        if len(matching_records) == 0:
            crash_route_list.append(
                (scenario_name, route_id)
            )
            continue

        if len(matching_records) > 1:
            print(
                f"WARNING: Skipping ambiguous route "
                f"{route_id}: {len(matching_records)} records"
            )
            crash_route_list.append(
                (scenario_name, route_id)
            )
            continue

        route_record = matching_records[0]
        matched_routes += 1

        record_success_status = (
            route_record.get("status")
            in ("Completed", "Perfect")
            and not get_infraction_status(
                route_record
            )
        )

        update_Ability(
            scenario_name,
            Ability_Statistic,
            record_success_status
        )

        update_Success(
            scenario_name,
            Success_Statistic,
            record_success_status
        )

        # ---------------------------------------------
        # Traffic Signs special handling
        # ---------------------------------------------

        if (
            scenario_name in Ability["Traffic_Signs"]
            and not record_success_status
        ):

            if town_name != current_town:
                current_town = town_name

                carla_map = load_offline_map(
                    current_town,
                    map_root
                )

                grp = GlobalRoutePlanner(
                    carla_map, 1.0
                )

            location_list = get_position(route)

            waypoint_route = get_waypoint_route(
                location_list, grp
            )

            if not waypoint_route:
                print(
                    f"WARNING: Empty waypoint route "
                    f"for route {route_id}"
                )
                continue

            count = 0
            junction_found = False

            for wp in waypoint_route:
                count += 1

                if wp.is_junction:
                    junction_found = True
                    break

            if not junction_found:
                print(
                    f"WARNING: No junction found "
                    f"for route {route_id}"
                )
                continue

            junction_completion = (
                float(count + 8)
                / len(waypoint_route)
            )

            record_completion = (
                route_record["scores"]["score_route"]
                / 100.0
            )

            infractions = route_record.get(
                "infractions", {}
            )

            stop_infraction = infractions.get(
                "stop_infraction", []
            )

            red_light_infraction = infractions.get(
                "red_light", []
            )

            if (
                record_completion > junction_completion
                and not stop_infraction
                and not red_light_infraction
            ):
                Ability_Statistic[
                    "Traffic_Signs"
                ][0] += 1

    # =================================================
    # ROUTE SUMMARY
    # =================================================

    print("\n========== ROUTE SUMMARY ==========")

    print(f"Routes in XML:       {len(routes)}")
    print(f"Routes evaluated:    {matched_routes}")
    print(f"Unmatched/ambiguous: {len(crash_route_list)}")

    print("===================================\n")

    # =================================================
    # ABILITY STATISTICS
    # =================================================

    print("\n========== ABILITY STATISTICS ==========")

    for ability, values in Ability_Statistic.items():
        print(
            f"{ability}: "
            f"success_count={values[0]}, "
            f"route_count={values[1]}"
        )

    print("========================================\n")

    # =================================================
    # SAFE ABILITY CALCULATION
    # =================================================

    Ability_Res = {}
    valid_scores = []
    missing_abilities = []

    for ability, values in Ability_Statistic.items():
        success_count, route_count = values

        if route_count > 0:
            score = success_count / route_count

            Ability_Res[ability] = score
            valid_scores.append(score)

        else:
            Ability_Res[ability] = None
            missing_abilities.append(ability)

            print(
                f"WARNING: {ability} has zero "
                "evaluated routes. Score = null."
            )

    if valid_scores:
        Ability_Res["mean"] = (
            sum(valid_scores) / len(valid_scores)
        )
    else:
        Ability_Res["mean"] = None

    Ability_Res["crashed"] = crash_route_list

    # =================================================
    # PRINT RESULTS
    # =================================================

    print("\n========== ABILITY RESULTS ==========")

    for ability in Ability:
        score = Ability_Res[ability]

        if score is None:
            print(f"{ability}: N/A")
        else:
            print(
                f"{ability}: "
                f"{score:.4f} "
                f"({score * 100:.2f}%)"
            )

    mean_score = Ability_Res["mean"]

    if mean_score is None:
        print("\nMean Ability Score: N/A")
    else:
        print(
            f"\nMean Ability Score: "
            f"{mean_score:.4f} "
            f"({mean_score * 100:.2f}%)"
        )

    print(
        f"Crashed Route num: "
        f"{len(crash_route_list)}"
    )

    if not complete:
        print(
            "\nWARNING: PARTIAL/INVALID BENCHMARK "
            "COVERAGE. Scores are diagnostic only."
        )

    if missing_abilities:
        print(
            "\nAbilities excluded from mean:"
        )

        for ability in missing_abilities:
            print(f"  - {ability}")

    print("=====================================\n")

    # =================================================
    # SAVE RESULTS
    # =================================================

    output_file = result_file.with_name(
        result_file.stem + "_ability.json"
    )

    Ability_Res["complete_route_matching"] = complete
    Ability_Res["matched_routes"] = matched_routes
    Ability_Res["expected_routes"] = len(routes)

    with open(output_file, "w") as f:
        json.dump(Ability_Res, f, indent=4)

    print(f"Result saved to {output_file}")
    print("Finished!")


if __name__ == "__main__":
    argparser = argparse.ArgumentParser()

    argparser.add_argument(
        "-f",
        "--file",
        default="leaderboard/data/bench2drive220.xml",
        help="Path to benchmark routes XML"
    )

    argparser.add_argument(
        "-r",
        "--result_file",
        required=True,
        help="Path to merged evaluation JSON"
    )

    argparser.add_argument(
        "--allow-partial",
        action="store_true",
        help=(
            "Allow diagnostic ability calculation "
            "when route matching is incomplete"
        )
    )

    args = argparser.parse_args()
    main(args)
