from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class OpType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN: _ClassVar[OpType]
    WRITE: _ClassVar[OpType]
    GUESS: _ClassVar[OpType]
    HEARTBEAT: _ClassVar[OpType]
    ELECTION: _ClassVar[OpType]
    ACK: _ClassVar[OpType]
    COMMIT: _ClassVar[OpType]
UNKNOWN: OpType
WRITE: OpType
GUESS: OpType
HEARTBEAT: OpType
ELECTION: OpType
ACK: OpType
COMMIT: OpType

class Proposal(_message.Message):
    __slots__ = ("epoch", "seq", "op", "value", "from_id")
    EPOCH_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    OP_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    FROM_ID_FIELD_NUMBER: _ClassVar[int]
    epoch: int
    seq: int
    op: OpType
    value: str
    from_id: str
    def __init__(self, epoch: _Optional[int] = ..., seq: _Optional[int] = ..., op: _Optional[_Union[OpType, str]] = ..., value: _Optional[str] = ..., from_id: _Optional[str] = ...) -> None: ...

class Ack(_message.Message):
    __slots__ = ("epoch", "seq", "from_id", "accepted")
    EPOCH_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    FROM_ID_FIELD_NUMBER: _ClassVar[int]
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    epoch: int
    seq: int
    from_id: str
    accepted: bool
    def __init__(self, epoch: _Optional[int] = ..., seq: _Optional[int] = ..., from_id: _Optional[str] = ..., accepted: bool = ...) -> None: ...

class Commit(_message.Message):
    __slots__ = ("epoch", "seq", "value")
    EPOCH_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    epoch: int
    seq: int
    value: str
    def __init__(self, epoch: _Optional[int] = ..., seq: _Optional[int] = ..., value: _Optional[str] = ...) -> None: ...

class Heartbeat(_message.Message):
    __slots__ = ("leader_id", "timestamp")
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    leader_id: str
    timestamp: int
    def __init__(self, leader_id: _Optional[str] = ..., timestamp: _Optional[int] = ...) -> None: ...

class Election(_message.Message):
    __slots__ = ("candidate_id", "epoch", "seq")
    CANDIDATE_ID_FIELD_NUMBER: _ClassVar[int]
    EPOCH_FIELD_NUMBER: _ClassVar[int]
    SEQ_FIELD_NUMBER: _ClassVar[int]
    candidate_id: str
    epoch: int
    seq: int
    def __init__(self, candidate_id: _Optional[str] = ..., epoch: _Optional[int] = ..., seq: _Optional[int] = ...) -> None: ...

class Vote(_message.Message):
    __slots__ = ("voter_id", "vote_for", "epoch")
    VOTER_ID_FIELD_NUMBER: _ClassVar[int]
    VOTE_FOR_FIELD_NUMBER: _ClassVar[int]
    EPOCH_FIELD_NUMBER: _ClassVar[int]
    voter_id: str
    vote_for: str
    epoch: int
    def __init__(self, voter_id: _Optional[str] = ..., vote_for: _Optional[str] = ..., epoch: _Optional[int] = ...) -> None: ...

class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ClientRequest(_message.Message):
    __slots__ = ("op", "value")
    OP_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    op: OpType
    value: str
    def __init__(self, op: _Optional[_Union[OpType, str]] = ..., value: _Optional[str] = ...) -> None: ...

class ClientResponse(_message.Message):
    __slots__ = ("success", "message", "current_target")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_TARGET_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    current_target: str
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., current_target: _Optional[str] = ...) -> None: ...
