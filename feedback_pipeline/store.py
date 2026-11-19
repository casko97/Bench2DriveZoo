"""SQLite metadata with immutable, verified content-addressed artifacts."""

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from dataclasses import asdict

from .contracts import Artifact, RECORD_TYPES, Record, Validation


class IntegrityError(ValueError):
    """A record or artifact failed integrity checks."""


class FeedbackStore:
    """One connection per instance; callers should close it or use a context manager."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.blobs = self.root / 'blobs'
        self.blobs.mkdir(exist_ok=True)
        self.connection = sqlite3.connect(str(self.root / 'feedback.sqlite3'), timeout=30)
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.execute('PRAGMA journal_mode=WAL')
        version = self.connection.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            self.connection.close()
            raise IntegrityError('Unsupported database version: {}'.format(version))
        with self.connection:
            self.connection.execute('CREATE TABLE IF NOT EXISTS records '
                                    '(id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)')
            self.connection.execute('CREATE INDEX IF NOT EXISTS records_kind ON records(kind)')
            self.connection.execute('PRAGMA user_version=1')

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _path(self, digest):
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise IntegrityError('Invalid artifact digest')
        return self.blobs / digest

    def put_artifact(self, data, media_type='application/octet-stream'):
        """Durably publish bytes before referencing them in a record transaction.

        An interrupted or failed record transaction can leave an unreferenced blob;
        it cannot publish a record referring to a partially written blob.
        """
        if not isinstance(data, bytes):
            raise TypeError('Artifact data must be bytes')
        digest = hashlib.sha256(data).hexdigest()
        path = self._path(digest)
        artifact = Artifact(digest, len(data), media_type)
        if path.exists():
            self.read_artifact(artifact)
            return artifact
        fd, name = tempfile.mkstemp(prefix='.pending-', dir=str(self.blobs))
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, str(path))
            directory = os.open(str(self.blobs), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return artifact

    def read_artifact(self, artifact):
        try:
            data = self._path(artifact.digest).read_bytes()
        except FileNotFoundError as exc:
            raise IntegrityError('Missing artifact: {}'.format(artifact.digest)) from exc
        if len(data) != artifact.size or hashlib.sha256(data).hexdigest() != artifact.digest:
            raise IntegrityError('Corrupt artifact: {}'.format(artifact.digest))
        return data

    def save(self, *records):
        """Atomically save records; referenced records may appear anywhere in the batch."""
        if len({record.id for record in records}) != len(records):
            raise IntegrityError('Duplicate record ID in batch')
        with self.connection:
            for record in records:
                self._validate(record)
                existing = self.connection.execute('SELECT kind FROM records WHERE id=?',
                                                   (record.id,)).fetchone()
                if existing and existing[0] != record.kind:
                    raise IntegrityError('Cannot change a record kind')
                if existing and self.get(record.id, verify_artifacts=False).references() != record.references():
                    raise IntegrityError('Cannot change record references')
                payload = json.dumps(asdict(record), allow_nan=False, sort_keys=True)
                self.connection.execute('INSERT OR REPLACE INTO records VALUES (?, ?, ?)',
                                        (record.id, record.kind, payload))
            for record in records:
                for kind, identifier in record.references():
                    target = self.connection.execute('SELECT kind FROM records WHERE id=?',
                                                     (identifier,)).fetchone()
                    if not target or target[0] != kind:
                        raise IntegrityError('Missing {} reference: {}'.format(kind, identifier))
                self._validate_links(record)

    def _validate_links(self, record):
        if record.kind == 'trigger' and self.get(record.frame_id, False).run_id != record.run_id:
            raise IntegrityError('Trigger frame belongs to another run')
        if record.kind in ('anchor', 'event_window'):
            run_id = self.get(record.trigger_id, False).run_id
            frames = ([record.frame_id] + record.observation_history
                      if record.kind == 'anchor' else record.frame_ids)
            if any(self.get(frame_id, False).run_id != run_id for frame_id in frames):
                raise IntegrityError('Event frame belongs to another run')
        if record.kind == 'preference':
            correction = self.get(record.correction_id, False)
            if self.get(correction.rerun_id, False).anchor_id != record.anchor_id:
                raise IntegrityError('Preference and correction anchors differ')

    def _validate(self, record):
        if not isinstance(record, Record) or RECORD_TYPES.get(record.kind) is not type(record):
            raise IntegrityError('Unknown record type')
        if not isinstance(record.id, str) or not record.id.strip():
            raise IntegrityError('Record ID is required')
        if record.schema_version != 1:
            raise IntegrityError('Unsupported record version')
        if record.status not in ('pending', 'complete', 'rejected', 'failed'):
            raise IntegrityError('Invalid record status')
        if record.status in ('rejected', 'failed') and not record.reason:
            raise IntegrityError('Rejected or failed records require a reason')
        for artifact in record.artifacts.values():
            if not isinstance(artifact, Artifact):
                raise IntegrityError('Invalid artifact reference')
            self.read_artifact(artifact)
        for name in ('state_match', 'validation'):
            validation = getattr(record, name, None)
            if validation is not None:
                if not isinstance(validation, Validation) or validation.status not in ('pending', 'accepted', 'rejected'):
                    raise IntegrityError('Invalid validation')
                if validation.status == 'rejected' and not validation.reasons:
                    raise IntegrityError('Rejected validation requires a reason')

    def get(self, identifier, verify_artifacts=True):
        row = self.connection.execute('SELECT kind, payload FROM records WHERE id=?',
                                      (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        kind, payload = row
        if kind not in RECORD_TYPES:
            raise IntegrityError('Unknown record type: {}'.format(kind))
        data = json.loads(payload)
        if data.get('schema_version') != 1:
            raise IntegrityError('Unsupported record version')
        data['artifacts'] = {name: Artifact(**value) for name, value in data['artifacts'].items()}
        for name in ('validation', 'state_match'):
            if name in data:
                data[name] = Validation(**data[name])
        record = RECORD_TYPES[kind](**data)
        if verify_artifacts:
            for artifact in record.artifacts.values():
                self.read_artifact(artifact)
        return record

    def list_ids(self, kind):
        if kind not in RECORD_TYPES:
            raise ValueError('Unknown record type: {}'.format(kind))
        rows = self.connection.execute('SELECT id FROM records WHERE kind=? ORDER BY id', (kind,))
        return [row[0] for row in rows]
