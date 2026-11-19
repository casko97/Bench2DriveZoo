"""Version 1 records. Positions, timestamps and units are supplied by producers."""

from dataclasses import dataclass, field
from typing import ClassVar, Dict, List, Optional, Protocol, Tuple


@dataclass
class Artifact:
    """An immutable blob identified by its SHA-256 digest."""
    digest: str
    size: int
    media_type: str = 'application/octet-stream'


@dataclass
class Validation:
    status: str = 'pending'  # pending, accepted, rejected
    reasons: List[str] = field(default_factory=list)
    metrics: Dict = field(default_factory=dict)


@dataclass
class Record:
    id: str
    status: str = 'pending'  # pending, complete, rejected, failed
    reason: Optional[str] = None
    metadata: Dict = field(default_factory=dict)
    artifacts: Dict[str, Artifact] = field(default_factory=dict)
    schema_version: int = 1
    kind: ClassVar[str] = ''

    def references(self) -> List[Tuple[str, str]]:
        return []


@dataclass
class TrainingRound(Record):
    kind: ClassVar[str] = 'training_round'
    policy_checkpoint: Dict = field(default_factory=dict)
    configuration: Dict = field(default_factory=dict)


@dataclass
class CollectionRun(Record):
    kind: ClassVar[str] = 'collection_run'
    round_id: str = ''
    route: Dict = field(default_factory=dict)
    scenario: Dict = field(default_factory=dict)
    simulator: Dict = field(default_factory=dict)
    seeds: Dict = field(default_factory=dict)

    def references(self):
        return [('training_round', self.round_id)]


@dataclass
class Frame(Record):
    kind: ClassVar[str] = 'frame'
    run_id: str = ''
    frame_number: int = 0
    simulation_time_seconds: float = 0.0
    coordinate_frames: Dict = field(default_factory=dict)
    ego_state: Dict = field(default_factory=dict)
    actor_states: List[Dict] = field(default_factory=list)
    traffic_lights: List[Dict] = field(default_factory=list)
    policy_context: Dict = field(default_factory=dict)

    def references(self):
        return [('collection_run', self.run_id)]


@dataclass
class Trigger(Record):
    kind: ClassVar[str] = 'trigger'
    run_id: str = ''
    frame_id: str = ''
    trigger_type: str = ''
    evidence: Dict = field(default_factory=dict)

    def references(self):
        return [('collection_run', self.run_id), ('frame', self.frame_id)]


@dataclass
class EventWindow(Record):
    kind: ClassVar[str] = 'event_window'
    trigger_id: str = ''
    frame_ids: List[str] = field(default_factory=list)
    requested_before_seconds: float = 0.0
    requested_after_seconds: float = 0.0
    actual_before_seconds: float = 0.0
    actual_after_seconds: float = 0.0

    def references(self):
        return [('trigger', self.trigger_id)] + [('frame', frame_id) for frame_id in self.frame_ids]


@dataclass
class Anchor(Record):
    kind: ClassVar[str] = 'anchor'
    trigger_id: str = ''
    frame_id: str = ''
    observation_history: List[str] = field(default_factory=list)

    def references(self):
        return [('trigger', self.trigger_id), ('frame', self.frame_id)] + [
            ('frame', frame_id) for frame_id in self.observation_history]


@dataclass
class Rerun(Record):
    kind: ClassVar[str] = 'rerun'
    anchor_id: str = ''
    simulator: Dict = field(default_factory=dict)
    seeds: Dict = field(default_factory=dict)
    state_match: Validation = field(default_factory=Validation)

    def references(self):
        return [('anchor', self.anchor_id)]


@dataclass
class Correction(Record):
    kind: ClassVar[str] = 'correction'
    rerun_id: str = ''
    provider: Dict = field(default_factory=dict)
    coordinate_frames: Dict = field(default_factory=dict)
    validation: Validation = field(default_factory=Validation)

    def references(self):
        return [('rerun', self.rerun_id)]


@dataclass
class Preference(Record):
    kind: ClassVar[str] = 'preference'
    anchor_id: str = ''
    correction_id: str = ''
    coordinate_frames: Dict = field(default_factory=dict)
    validation: Validation = field(default_factory=Validation)

    def references(self):
        return [('anchor', self.anchor_id), ('correction', self.correction_id)]


@dataclass
class DatasetSnapshot(Record):
    kind: ClassVar[str] = 'dataset_snapshot'
    round_id: str = ''
    preference_ids: List[str] = field(default_factory=list)
    configuration: Dict = field(default_factory=dict)

    def references(self):
        return [('training_round', self.round_id)] + [
            ('preference', preference_id) for preference_id in self.preference_ids]


class FeedbackProvider(Protocol):
    """Future expert adapters generate corrections; storage does not invoke them."""
    def generate(self, anchor: Anchor, rerun: Rerun) -> Correction:
        ...


RECORD_TYPES = {cls.kind: cls for cls in (TrainingRound, CollectionRun, Frame,
                Trigger, EventWindow, Anchor, Rerun, Correction, Preference, DatasetSnapshot)}
