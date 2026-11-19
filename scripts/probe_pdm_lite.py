#!/usr/bin/env python3
"""Standalone PDM-Lite smoke test on a disposable CARLA server.

Run from the pinned CARLA Garage checkout with its team_code, leaderboard_autopilot
and scenario_runner_autopilot on PYTHONPATH, plus this worktree. This changes
world settings and creates actors. It is not a Bench2Drive scenario test.
"""
import argparse
import json
import queue

import carla
from autopilot import AutoPilot
from leaderboard.utils.route_manipulation import interpolate_trajectory
from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
from feedback_pipeline.pdm_lite import PdmLiteAdapter


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--ticks', type=int, default=100)
    p.add_argument('--handoff-ticks', type=int, default=0)
    p.add_argument('--route-following-warmup', action='store_true')
    p.add_argument('--revision', required=True)
    p.add_argument('--town', default='Town07')
    args = p.parse_args()
    client = carla.Client('127.0.0.1', args.port)
    client.set_timeout(60)
    world = client.load_world(args.town)
    original = world.get_settings()
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = .05
    world.apply_settings(settings)
    ego = imu = adapter = None
    try:
        CarlaDataProvider.set_client(client)
        CarlaDataProvider.set_world(world)
        spawn = world.get_map().get_spawn_points()[0]
        start_wp = world.get_map().get_waypoint(spawn.location)
        waypoint = start_wp
        for _ in range(45):
            candidates = waypoint.next(2.0)
            if not candidates:
                break
            waypoint = candidates[0]
        gps, route = interpolate_trajectory([start_wp.transform.location, waypoint.transform.location])
        ego = CarlaDataProvider.request_new_actor('vehicle.tesla.model3', spawn, rolename='hero')
        if ego is None:
            raise RuntimeError('unable to spawn hero')
        sensor_bp = world.get_blueprint_library().find('sensor.other.imu')
        imu = world.spawn_actor(sensor_bp, carla.Transform(), attach_to=ego)
        imu_queue = queue.Queue()
        imu.listen(imu_queue.put)
        def make_adapter(gps_plan, world_plan):
            return PdmLiteAdapter(AutoPilot, CarlaDataProvider, config_path='', route_index=0,
                                  world=world, ego=ego, gps_route=gps_plan, world_route=world_plan,
                                  scenario_state=[], provenance={'revision': args.revision})

        def step_expert(active):
            frame = world.tick()
            CarlaDataProvider.on_carla_tick()
            measurement = imu_queue.get(timeout=30)
            while measurement.frame < frame:
                measurement = imu_queue.get(timeout=30)
            if measurement.frame != frame:
                raise RuntimeError('IMU frame mismatch')
            data = {'imu': (frame, [measurement.accelerometer.x, measurement.accelerometer.y,
                                    measurement.accelerometer.z, measurement.gyroscope.x,
                                    measurement.gyroscope.y, measurement.gyroscope.z, measurement.compass])}
            control = active.run_step(data, world.get_snapshot().timestamp.elapsed_seconds)
            ego.apply_control(control)
            return control

        if args.route_following_warmup and args.handoff_ticks:
            adapter = make_adapter(gps, route)
            for _ in range(args.handoff_ticks):
                step_expert(adapter)
            adapter.close()
            adapter = None
        else:
            for _ in range(args.handoff_ticks):
                ego.apply_control(carla.VehicleControl(throttle=0.8))
                world.tick()
                CarlaDataProvider.on_carla_tick()
        handoff_speed = ego.get_velocity().length()
        closest = min(range(len(route)), key=lambda i: route[i][0].location.distance(ego.get_location()))
        handoff_route_distance = route[closest][0].location.distance(ego.get_location())
        if args.route_following_warmup:
            gps, route = gps[closest:], route[closest:]
        adapter = make_adapter(gps, route)
        start = ego.get_location()
        controls = []
        for _ in range(args.ticks):
            control = step_expert(adapter)
            controls.append([control.steer, control.throttle, control.brake])
        print(json.dumps({'map': world.get_map().name, 'ticks': args.ticks,
                          'progress_m': start.distance(ego.get_location()),
                          'handoff_ticks': args.handoff_ticks, 'handoff_speed_mps': handoff_speed,
                          'handoff_route_distance_m': handoff_route_distance,
                          'route_following_warmup': args.route_following_warmup,
                          'controls': controls, 'expert_revision': args.revision}, indent=2))
    finally:
        if adapter is not None:
            adapter.close()
        if imu is not None:
            imu.stop()
            imu.destroy()
        if ego is not None:
            ego.destroy()
        world.apply_settings(original)


if __name__ == '__main__':
    main()
