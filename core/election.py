"""
Exports ``ElectionManager``, the component responsible for deciding votes
during leader election based on epoch and sequence comparison.
"""

from __future__ import annotations


__all__ = ["ElectionManager"]

class ElectionManager:
    def __init__(self, node_id: str):
        """
        Initialize a new election manager bound to a node.

        :param node_id: ID of the node that owns this election manager.
        """
        self.node_id: str = node_id
        self.voted_for: str | None = None

    def decide_vote(
        self,
        candidate_id: str,
        candidate_epoch: int,
        candidate_seq: int,
        self_epoch: int,
        self_seq: int,
    ) -> str:
        """
        Determine which node to vote for based on epoch and sequence numbers.

        Note:
            Comparison rules:
            1. Higher epoch wins.
            2. If equal, higher sequence wins.
            3. If also equal, lowest node ID wins (tie-breaker).

        :param candidate_id: ID of the candidate requesting the vote.
        :param candidate_epoch: Candidate's epoch.
        :param candidate_seq: Candidate's sequence number.
        :param self_epoch: Local node's epoch.
        :param self_seq: Local node's sequence number.
        :return: The node ID that receives this node's vote.
        """
        if candidate_epoch > self_epoch:
            winner = candidate_id
        elif candidate_epoch < self_epoch:
            winner = self.node_id
        else:
            if candidate_seq > self_seq:
                winner = candidate_id
            elif candidate_seq < self_seq:
                winner = self.node_id
            else:
                winner = candidate_id if candidate_id < self.node_id else self.node_id
        self.voted_for = winner
        return winner
