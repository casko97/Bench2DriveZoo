import hashlib
import sqlite3

import pytest

from feedback_pipeline import (Anchor, CollectionRun, Correction, DatasetSnapshot, EventWindow,
                               FeedbackStore, Frame, IntegrityError, Preference,
                               Rerun, TrainingRound, Trigger, Validation)


def test_round_trip_linked_records_and_artifacts(tmp_path):
    with FeedbackStore(tmp_path) as store:
        image = store.put_artifact(b'camera bytes', 'image/png')
        trajectory = store.put_artifact(b'trajectory bytes')
        records = [
            TrainingRound('round-1', policy_checkpoint={'path': 'model.pth', 'sha256': 'abc'}),
            CollectionRun('run-1', round_id='round-1', route={'id': 'route-1'},
                          scenario={'name': 'turn'}, simulator={'version': '0.9.15'}, seeds={'traffic': 0}),
            Frame('frame-1', run_id='run-1', frame_number=12, simulation_time_seconds=0.6,
                  coordinate_frames={'ego': 'vehicle'}, ego_state={'speed_mps': 2},
                  artifacts={'front': image}),
            Trigger('trigger-1', run_id='run-1', frame_id='frame-1',
                    trigger_type='low_ttc', evidence={'ttc_seconds': 1.2}),
            EventWindow('window-1', trigger_id='trigger-1', frame_ids=['frame-1'],
                        requested_before_seconds=2, actual_before_seconds=0.1),
            Anchor('anchor-1', trigger_id='trigger-1', frame_id='frame-1', observation_history=['frame-1']),
            Rerun('rerun-1', anchor_id='anchor-1', state_match=Validation('accepted', metrics={'position_m': 0.01})),
            Correction('correction-1', rerun_id='rerun-1', provider={'name': 'pdm-lite', 'version': 'rev'},
                       validation=Validation('accepted'), artifacts={'trajectory': trajectory}),
            Preference('pair-1', anchor_id='anchor-1', correction_id='correction-1',
                       validation=Validation('accepted')),
            DatasetSnapshot('dataset-1', round_id='round-1', preference_ids=['pair-1']),
        ]
        store.save(*reversed(records))
        assert [store.get(record.id) for record in records] == records
        assert store.read_artifact(image) == b'camera bytes'
        assert store.list_ids('preference') == ['pair-1']
    with FeedbackStore(tmp_path) as store:
        assert store.get('pair-1').correction_id == 'correction-1'


def test_incomplete_and_rejected_records(tmp_path):
    with FeedbackStore(tmp_path) as store:
        store.save(TrainingRound('r'), CollectionRun('run', round_id='r'), Frame('f', run_id='run'),
                   Trigger('t', run_id='run', frame_id='f'), Anchor('a', trigger_id='t', frame_id='f'),
                   Rerun('rerun', anchor_id='a', status='failed', reason='scenario stopped early',
                         state_match=Validation('rejected', reasons=['missing actor'])))
        assert store.get('rerun').state_match.reasons == ['missing actor']
        assert store.get('f').status == 'pending'
        with pytest.raises(IntegrityError, match='require a reason'):
            store.save(TrainingRound('invalid', status='rejected'))


def test_failed_transaction_does_not_publish_any_records(tmp_path):
    with FeedbackStore(tmp_path) as store:
        artifact = store.put_artifact(b'finished blob')
        with pytest.raises(IntegrityError, match='Missing training_round'):
            store.save(TrainingRound('new', artifacts={'data': artifact}),
                       CollectionRun('bad', round_id='absent'))
        with pytest.raises(KeyError):
            store.get('new')
        assert store.read_artifact(artifact) == b'finished blob'


def test_interrupted_artifact_publish_leaves_no_visible_blob(tmp_path, monkeypatch):
    def interrupted(*args):
        raise OSError('simulated interrupted rename')

    with FeedbackStore(tmp_path) as store:
        monkeypatch.setattr('feedback_pipeline.store.os.replace', interrupted)
        with pytest.raises(OSError, match='interrupted'):
            store.put_artifact(b'incomplete')
        assert list((tmp_path / 'blobs').iterdir()) == []
        assert store.list_ids('training_round') == []


def test_missing_and_corrupted_artifacts_are_detected(tmp_path):
    with FeedbackStore(tmp_path) as store:
        artifact = store.put_artifact(b'original')
        store.save(TrainingRound('r', artifacts={'x': artifact}))
        blob = tmp_path / 'blobs' / artifact.digest
        blob.write_bytes(b'corrupted')
        with pytest.raises(IntegrityError, match='Corrupt artifact'):
            store.get('r')
        assert store.get('r', verify_artifacts=False).id == 'r'
        blob.unlink()
        with pytest.raises(IntegrityError, match='Missing artifact'):
            store.get('r')


def test_invalid_references_and_versions_are_rejected(tmp_path):
    with FeedbackStore(tmp_path) as store:
        store.save(TrainingRound('r'), CollectionRun('run', round_id='r'))
        with pytest.raises(IntegrityError, match='Missing frame'):
            store.save(Trigger('t', run_id='run', frame_id='r'))
        with pytest.raises(IntegrityError, match='version'):
            store.save(TrainingRound('new', schema_version=2))
        with pytest.raises(IntegrityError, match='record kind'):
            store.save(CollectionRun('r', round_id='r'))
    connection = sqlite3.connect(str(tmp_path / 'feedback.sqlite3'))
    connection.execute('PRAGMA user_version=2')
    connection.close()
    with pytest.raises(IntegrityError, match='database version'):
        FeedbackStore(tmp_path)


def test_deduplicated_blobs_and_digest_validation(tmp_path):
    with FeedbackStore(tmp_path) as store:
        first = store.put_artifact(b'same')
        second = store.put_artifact(b'same', 'image/png')
        assert first.digest == second.digest == hashlib.sha256(b'same').hexdigest()
        assert len(list((tmp_path / 'blobs').iterdir())) == 1
        first.digest = '../../escape'
        with pytest.raises(IntegrityError, match='digest'):
            store.read_artifact(first)


def test_cross_run_and_cross_anchor_links_are_rejected(tmp_path):
    with FeedbackStore(tmp_path) as store:
        store.save(TrainingRound('r'), CollectionRun('run-a', round_id='r'),
                   CollectionRun('run-b', round_id='r'), Frame('a', run_id='run-a'),
                   Frame('b', run_id='run-b'), Trigger('t', run_id='run-a', frame_id='a'),
                   Anchor('anchor-a', trigger_id='t', frame_id='a'),
                   Anchor('anchor-other', trigger_id='t', frame_id='a'),
                   Rerun('rerun', anchor_id='anchor-a'), Correction('c', rerun_id='rerun'))
        with pytest.raises(IntegrityError, match='another run'):
            store.save(Trigger('bad', run_id='run-a', frame_id='b'))
        with pytest.raises(IntegrityError, match='another run'):
            store.save(EventWindow('bad-window', trigger_id='t', frame_ids=['b']))
        with pytest.raises(IntegrityError, match='anchors differ'):
            store.save(Preference('bad-pair', anchor_id='anchor-other', correction_id='c'))
        with pytest.raises(IntegrityError, match='Cannot change record references'):
            store.save(Frame('a', run_id='run-b'))
