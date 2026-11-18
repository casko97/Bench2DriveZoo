from team_code.collision_stop import SustainedCollisionStop


def test_sustained_collision_requires_distinct_consecutive_frames():
    stop = SustainedCollisionStop(3)
    stop.observe(10, 100, accepted=True)
    stop.observe(10, 100)
    stop.observe(10, 101)
    assert stop.take_stop() is None
    stop.observe(10, 102)
    assert stop.take_stop() == {'actor_id': 10, 'frame': 102, 'consecutive_frames': 3}


def test_gap_or_other_actor_requires_new_recorded_collision():
    stop = SustainedCollisionStop(3)
    stop.observe(10, 100, accepted=True)
    stop.observe(10, 102)
    stop.observe(11, 103)
    stop.observe(11, 104)
    assert stop.take_stop() is None
    stop.observe(11, 105, accepted=True)
    stop.observe(11, 106)
    stop.observe(11, 107)
    assert stop.take_stop()['actor_id'] == 11
    stop.reset()
    assert stop.take_stop() is None


def test_disabled_collision_stop():
    stop = SustainedCollisionStop(0)
    for frame in range(10):
        stop.observe(1, frame, accepted=True)
    assert stop.take_stop() is None
