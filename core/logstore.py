"""
Exports ``LogStore``, the component responsible for persistent storage of
proposal and commit records used by each node.
"""

from __future__ import annotations

import pickle
import os
from typing import List, Dict, Any

__all__ = ["LogStore"]


class LogStore:
    def __init__(self, path: str):
        """
        Initialize the log store and load existing entries from disk.

        :param path: Filesystem path to the persisted log file.
        """
        self.path: str = path
        self.logs: List[Dict[str, Any]] = self._load()

    # ---------------------------------------------------------
    # Load
    # ---------------------------------------------------------
    def _load(self) -> list[dict]:
        """
        Load persisted logs from disk.

        Note:
            Only ``list[dict]`` structures are accepted. Invalid or unreadable
            files result in a reset to an empty list.

        :return: Loaded log entries or an empty list on failure.
        """
        if not os.path.exists(self.path):
            return []

        try:
            with open(self.path, "rb") as f:
                data = pickle.load(f)
                if isinstance(data, list):
                    return data
                print(f"[LogStore] Invalid log structure, resetting: {type(data)}")
        except (pickle.UnpicklingError, EOFError) as e:
            print(f"[LogStore] Failed to unpickle {self.path}: {e}")
        except OSError as e:
            print(f"[LogStore] OS error while reading {self.path}: {e}")

        return []

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------
    def _save(self):
        """
        Persist the current log entries to disk.

        :return: None
        """
        try:
            with open(self.path, "wb") as f:
                pickle.dump(self.logs, f)  # noqa
        except OSError as e:
            print(f"[LogStore] Failed to save log file {self.path}: {e}")

    # ---------------------------------------------------------
    # API used by NodeServer
    # ---------------------------------------------------------
    def append(
        self,
        epoch: int,
        seq: int,
        op: int,
        value: str,
        status: str = "PROPOSED",
    ):
        """
        Append a new log entry.

        :param epoch: Epoch number associated with the entry.
        :param seq: Sequence number associated with the entry.
        :param op: Operation code (WRITE/GUESS/etc.).
        :param value: Value associated with the operation.
        :param status: Entry status (default: ``PROPOSED``).
        :return: None
        """
        entry = {
            "epoch": epoch,
            "seq": seq,
            "op": op,
            "value": value,
            "status": status,
        }
        self.logs.append(entry)
        self._save()

    def commit(self, epoch: int, seq: int):
        """
        Mark an entry as committed.

        :param epoch: Epoch number of the entry.
        :param seq: Sequence number of the entry.
        :return: None
        """
        for e in self.logs:
            if e["epoch"] == epoch and e["seq"] == seq:
                e["status"] = "COMMITTED"
        self._save()

    # ---------------------------------------------------------
    # last_value(): return last committed value
    # ---------------------------------------------------------
    def last_value(self) -> str | None:
        """
        Retrieve the last committed value.

        :return: The most recent committed value or ``None`` if none exist.
        """
        for e in reversed(self.logs):
            if e.get("status") == "COMMITTED":
                return e.get("value")
        return None

    # ---------------------------------------------------------
    # entries property (used by NodeServer recovery)
    # ---------------------------------------------------------
    @property
    def entries(self) -> List[Dict[str, Any]]:
        """
        Return all stored log entries.

        :return: A list of log records.
        """
        return self.logs
