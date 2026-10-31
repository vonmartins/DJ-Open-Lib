"""Opaque, stable identifiers for tracks and playlist nodes."""

import uuid
from typing import NewType

TrackId = NewType("TrackId", uuid.UUID)
NodeId = NewType("NodeId", uuid.UUID)


def new_track_id() -> TrackId:
    return TrackId(uuid.uuid4())


def new_node_id() -> NodeId:
    return NodeId(uuid.uuid4())
