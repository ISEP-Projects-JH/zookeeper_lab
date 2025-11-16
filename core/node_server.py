"""
Core server module providing ``NodeServer`` and the ``serve`` entry function.

This module forms the primary RPC service for each node and is invoked by
the launcher ``python -m scripts.run_nodes``.
"""
from typing import NoReturn

import grpc
import time
import threading
import os
from concurrent import futures
from rich.console import Console
from zk import zookeeper_pb2, zookeeper_pb2_grpc
from .election import ElectionManager
from .logstore import LogStore
from .leader import LeaderCoordinator
from .config import config_path

__all__ = ["NodeServer", "serve"]

console = Console()


class NodeServer(zookeeper_pb2_grpc.NodeServiceServicer):
    """
    Node server implementing RPC handlers, leader election, replication logic,
    heartbeat exchange, and client request processing.

    :param node_id: ID of this node (e.g., "Node1").
    :param port: Local listening port.
    :param peers: Ports of peer nodes.
    :param base_port: Base port used for port-index mapping.
    """

    def __init__(self, node_id: str, port: int, peers: list[int], base_port: int):
        """
        Initialize a node server instance.

        Note:
            This constructor sets up node identity, networking configuration,
            subsystem components (log store, election manager, leader coordinator),
            and liveness tracking structures.

        :param node_id: Identifier of this node (e.g., "Node1").
        :param port: Local listening port.
        :param peers: Ports of peer nodes.
        :param base_port: Base port used for node-to-port mapping.
        """
        self.guesses: list | None = None
        self.current_target: int | None = None
        self.node_id: str = node_id
        self.port: int = port
        self.peers: list[int] = peers
        self.base_port: int = base_port

        # State management
        self.role: str = "follower"
        self.leader_id: str | None = None
        self.epoch: int = 0
        self.seq: int = 0

        # Subsystems
        self.log: LogStore = LogStore(f"logs_{node_id}.pkl")
        self.election: ElectionManager = ElectionManager(node_id)
        self.leader_coordinator: LeaderCoordinator | None = None

        # Node liveness tracking
        self.alive_nodes: dict[str, int] = {node_id: port}
        self.last_heartbeat: dict[str, float] = {node_id: time.time()}
        self.config_path = config_path  # absolute config/nodes.txt
        os.makedirs("config", exist_ok=True)

        console.log(f"[INIT] Node {node_id} started on port {port} with peers {peers}")

    def make_heartbeat(self) -> zookeeper_pb2.Heartbeat:
        """
        Construct a standard heartbeat message.

        :return: A Heartbeat protobuf message.
        """

        return zookeeper_pb2.Heartbeat(
            leader_id=self.node_id,
            timestamp=int(time.time())
        )

    def SendProposal(
            self,
            request: zookeeper_pb2.Proposal,
            context: grpc.ServicerContext
    ) -> zookeeper_pb2.Ack:
        """
        Handle proposal RPC from the leader.

        Note:
            Followers append the proposal to their log and reply with an ACK.

        :param request: Proposal message from leader.
        :param context: RPC context.
        :return: Ack protobuf response.
        """
        console.log(f"[{self.node_id}] Received Proposal: {request.value}")
        self.log.append(request.epoch, request.seq, request.op, request.value)
        ack = zookeeper_pb2.Ack(
            epoch=request.epoch, seq=request.seq, from_id=self.node_id, accepted=True
        )
        return ack

    def SendCommit(
            self,
            request: zookeeper_pb2.Commit,
            context: grpc.ServicerContext,
    ) -> zookeeper_pb2.Empty:
        """
        Handle commit RPC from the leader.

        Note:
            The follower marks the entry as committed, updates its local target
            value, and appends a persisted record.

        :param request: Commit instruction from the leader.
        :param context: RPC context.
        :return: Empty protobuf response.
        """
        console.log(f"[{self.node_id}] Commit seq={request.seq}, value={request.value}")
        self.log.commit(request.epoch, request.seq)
        try:
            # Update follower-local target value
            self.current_target = int(request.value)

            # Persist the last committed value
            if hasattr(self.log, "append"):
                self.log.append(
                    request.epoch,
                    request.seq,
                    zookeeper_pb2.WRITE,
                    str(request.value),
                )

            console.log(f"[{self.node_id}] Updated current_target to {self.current_target}")
        except Exception as e:
            console.log(f"[{self.node_id}] Commit update failed: {e}")

        return zookeeper_pb2.Empty()

    def KillSelf(
            self,
            request: zookeeper_pb2.Empty,
            context: grpc.ServicerContext,
    ) -> NoReturn:
        """
        Kill RPC used for testing node failure.

        Note:
            The node terminates its own process immediately upon receiving
            this RPC call. This function never returns.

        :param request: Empty kill request.
        :param context: RPC context.
        """
        console.log(f"[{self.node_id}] Received kill signal, shutting down...")
        os._exit(0)  # noqa

    def SendHeartbeat(
            self,
            request: zookeeper_pb2.Heartbeat,
            context: grpc.ServicerContext,
    ) -> zookeeper_pb2.Empty:
        """
        Handle heartbeat RPC.

        Note:
            This RPC is bidirectional:
            - Followers receive heartbeats from the leader.
            - The leader receives reverse heartbeats from followers.
            - Both sides update ``alive_nodes`` and heartbeat timestamps.

        :param request: Heartbeat message from peer.
        :param context: RPC context.
        :return: Empty protobuf response.
        """
        sender_id = request.leader_id
        ts = request.timestamp
        now = time.time()

        # Defensive check
        if not sender_id.startswith("Node"):
            console.log(f"[{self.node_id}] Ignoring external heartbeat from {sender_id}")
            return zookeeper_pb2.Empty()

        # Follower receiving leader heartbeat
        if self.role != "leader":
            self.leader_id = sender_id
            self.role = "follower"
            self.last_heartbeat[sender_id] = ts
            self.last_heartbeat[self.node_id] = now
            self.alive_nodes[self.node_id] = self.port

            console.log(f"[{self.node_id}] Heartbeat from {sender_id}")

            # Report back to the leader
            if sender_id != self.node_id:
                try:
                    leader_port = self.get_port_by_id(sender_id)
                    with grpc.insecure_channel(f"localhost:{leader_port}") as ch:
                        stub = zookeeper_pb2_grpc.NodeServiceStub(ch)
                        hb = self.make_heartbeat()
                        stub.SendHeartbeat(hb)
                except Exception as e:
                    console.log(f"[{self.node_id}] Failed to report back to leader: {e}")
            return zookeeper_pb2.Empty()

        # Leader receiving follower heartbeat
        else:
            follower_id = sender_id
            follower_port = self.get_port_by_id(follower_id)

            if follower_id.startswith("Node"):
                self.alive_nodes[follower_id] = follower_port
                self.last_heartbeat[follower_id] = ts
                console.log(f"[{self.node_id}] Alive follower: {follower_id}")

                # Periodically refresh config
                self.write_nodes_config()
            return zookeeper_pb2.Empty()

    def StartElection(
            self,
            request: zookeeper_pb2.Election,
            context: grpc.ServicerContext,
    ) -> zookeeper_pb2.Vote:
        """
        Handle incoming election request and return this node's vote.

        Note:
            The vote decision is delegated to ``ElectionManager`` based on epoch
            and sequence comparison.

        :param request: Election request message from a candidate.
        :param context: RPC context.
        :return: Vote protobuf indicating which node this server votes for.
        """
        console.log(f"[{self.node_id}] Election request from {request.candidate_id}")
        vote_for = self.election.decide_vote(
            candidate_id=request.candidate_id,
            candidate_epoch=request.epoch,
            candidate_seq=request.seq,
            self_epoch=self.epoch,
            self_seq=self.seq,
        )
        vote = zookeeper_pb2.Vote(voter_id=self.node_id, vote_for=vote_for, epoch=request.epoch)
        return vote

    def broadcast_proposal(
            self,
            epoch: int,
            seq: int,
            op: zookeeper_pb2.OpType,
            value: str,
    ) -> bool:
        """
        Broadcast a proposal to all followers and wait for majority ACKs.

        Note:
            The leader counts acknowledgements from peers. A majority is required
            for the proposal to be considered replicated.

        :param epoch: Epoch number of the proposal.
        :param seq: Sequence number of the proposal.
        :param op: Operation code (WRITE/GUESS/etc).
        :param value: Proposal value.
        :return: True if a majority of followers acknowledged; otherwise False.
        """
        acks = 1  # noqa Leader counts itself
        for peer_port in self.peers:
            try:
                with grpc.insecure_channel(f"localhost:{peer_port}") as ch:
                    stub = zookeeper_pb2_grpc.NodeServiceStub(ch)
                    req = zookeeper_pb2.Proposal(value=str(value), epoch=epoch, seq=seq, op=op)
                    resp = stub.SendProposal(req)
                    if resp.accepted:
                        acks += 1
            except grpc.RpcError:
                # follower unreachable, just skip
                continue
        return acks >= (len(self.peers) + 1) // 2 + 1

    def broadcast_commit(
            self,
            epoch: int,
            seq: int,
            value: str,
    ) -> None:
        """
        Broadcast a commit instruction to all followers.

        Note:
            The leader sends a ``Commit`` message to every follower. Followers
            apply the commit and update their local state accordingly.

        :param epoch: Epoch number of the committed entry.
        :param seq: Sequence number of the committed entry.
        :param value: Committed value.
        :return: None
        """
        for peer_port in self.peers:
            try:
                with grpc.insecure_channel(f"localhost:{peer_port}") as ch:
                    stub = zookeeper_pb2_grpc.NodeServiceStub(ch)
                    stub.SendCommit(zookeeper_pb2.Commit(epoch=epoch, seq=seq, value=str(value)))
            except grpc.RpcError:
                # follower unreachable / RPC failure → skip
                continue

    def SubmitRequest(
            self,
            request: zookeeper_pb2.ClientRequest,
            context: grpc.ServicerContext  # noqa
    ) -> zookeeper_pb2.ClientResponse:
        """
        Handle client requests routed to this node.

        Note:
            Followers forward all client requests to the current leader.
            The leader processes WRITE, GUESS, and READ operations:

            - WRITE:
                Creates a new proposal, replicates it to followers, commits on
                majority, and updates the current target.

            - GUESS:
                Accumulates guesses until three values are collected, selects the
                closest guess, commits it, and updates the target.

            - READ (UNKNOWN op):
                Returns the last committed value or an appropriate fallback.

        :param request: ClientRequest protobuf containing op/value.
        :param context: Sentinel Parameter. (unused, maintained for grpc API)
        :return: ClientResponse protobuf containing result or error info.
        """
        op = request.op
        value = request.value

        if self.role != "leader":
            if not self.leader_id:
                return zookeeper_pb2.ClientResponse(message="No leader available.")
            try:
                leader_port = self.get_port_by_id(self.leader_id)
                with grpc.insecure_channel(f"localhost:{leader_port}") as ch:
                    stub = zookeeper_pb2_grpc.ClientServiceStub(ch)
                    return stub.SubmitRequest(request)
            except Exception as e:
                return zookeeper_pb2.ClientResponse(message=f"Leader unreachable: {e}")

        # WRITE operation
        if op == zookeeper_pb2.WRITE:
            self.seq += 1
            epoch, seq = self.epoch, self.seq
            self.current_target = int(value)
            self.guesses = []

            console.log(f"[{self.node_id}] Broadcasting proposal seq={seq}, value={value}")
            self.log.append(epoch, seq, op, value)

            # Replicate proposal
            majority_ok = self.broadcast_proposal(epoch, seq, op, value)
            if not majority_ok:
                return zookeeper_pb2.ClientResponse(message="Failed to replicate to majority — aborting.")

            # commit
            self.log.commit(epoch, seq)
            self.broadcast_commit(epoch, seq, value)

            msg = f"🎯 New target set to {value} (committed)"
            return zookeeper_pb2.ClientResponse(message=msg, current_target=value)

        # GUESS operation
        elif op == zookeeper_pb2.GUESS:
            if not hasattr(self, "current_target"):
                return zookeeper_pb2.ClientResponse(message="No target has been set yet — please wait for WRITE.")
            if self.guesses is None:
                self.guesses = []

            guess = int(value)
            self.guesses.append(guess)
            msg = f"Received guess {guess}"

            if len(self.guesses) >= 3:
                winner = min(self.guesses, key=lambda g: abs(g - self.current_target))
                self.seq += 1
                epoch, seq = self.epoch, self.seq

                # 1. append proposal locally
                self.log.append(epoch, seq, zookeeper_pb2.WRITE, str(winner))

                # 2. replicate to majority
                majority_ok = self.broadcast_proposal(epoch, seq, zookeeper_pb2.WRITE, str(winner))
                if not majority_ok:
                    return zookeeper_pb2.ClientResponse(message="Failed to replicate GUESS winner")

                # 3. commit locally
                self.log.commit(epoch, seq)

                # 4. notify followers
                self.broadcast_commit(epoch, seq, str(winner))

                # 5. update target
                self.current_target = winner
                self.guesses = []

                msg += f" → Closest guess: {winner} (new target)"
                return zookeeper_pb2.ClientResponse(message=msg, current_target=str(self.current_target))

            return zookeeper_pb2.ClientResponse(message=msg)

        # READ operation (op == UNKNOWN)
        elif op == zookeeper_pb2.UNKNOWN:
            val: int | None
            try:
                if hasattr(self, "current_target"):
                    val = self.current_target
                elif hasattr(self.log, "last_value"):
                    val = self.log.last_value()
                elif hasattr(self.log, "entries") and self.log.entries:
                    val = self.log.entries[-1]["value"]
                else:
                    val = None
            except Exception as e:
                console.log(f"[{self.node_id}] Read failed safely: {e}")
                val = None

            if val is None:
                return zookeeper_pb2.ClientResponse(
                    message="No committed value available yet.", current_target="N/A"
                )

            return zookeeper_pb2.ClientResponse(
                message="Current committed value", current_target=str(val)
            )
        # Invalid op
        else:
            return zookeeper_pb2.ClientResponse(message="Invalid operation")

    def become_leader(self) -> None:
        """
        Transition this node into the leader role.

        Note:
            Initializes the leader coordinator, updates cluster configuration,
            starts heartbeat monitoring, and attempts to recover the last committed
            target value from the log.

        :return: None
        """
        self.role = "leader"
        self.leader_id = self.node_id
        console.log(f"[{self.node_id}] Became LEADER (epoch={self.epoch})")

        self.leader_coordinator = LeaderCoordinator(
            node_id=self.node_id,
            base_port=self.base_port,
            peers=self.peers,
            write_nodes_callback=self.write_nodes_config,
        )
        self.leader_coordinator.start()
        self.write_nodes_config()

        threading.Thread(target=self.monitor_heartbeat, daemon=True).start()
        console.log(f"[{self.node_id}] Heartbeat monitor started as leader.")
        try:
            if hasattr(self.log, "entries") and self.log.entries:
                last = self.log.entries[-1]
                self.current_target = int(last["value"])
                console.log(f"[{self.node_id}] Recovered target from log: {self.current_target}")
        except Exception as e:
            console.log(f"[{self.node_id}] Failed to recover target: {e}")

    def write_nodes_config(
            self,
            active_nodes: dict[str, int] | None = None,
    ) -> None:
        """
        Write the current cluster node status to ``config/nodes.txt``.

        Note:
            Only the leader writes this file. Followers ignore this call.

        :param active_nodes: Optional explicit node map; falls back to ``alive_nodes``.
        :return: None
        """
        try:
            if self.role != "leader":
                return
            config_path.parent.mkdir(parents=True, exist_ok=True)
            nodes = active_nodes or self.alive_nodes
            with config_path.open("w") as f:
                f.write("# Auto-generated by leader\n")
                for nid, port in sorted(nodes.items()):
                    role = "leader" if nid == self.leader_id else "follower"
                    f.write(f"{role} {nid} {port}\n")
            console.log(f"[{self.node_id}] Updated {config_path}")
        except Exception as e:
            console.log(f"[{self.node_id}] Failed to update config: {e}")

    def get_port_by_id(self, node_id: str) -> int:
        """
        Resolve a node's TCP port from its node ID.

        :param node_id: Node identifier (e.g., ``"Node3"``).
        :return: Port number for that node.
        """
        try:
            idx = int(node_id.replace("Node", ""))
            return self.base_port + idx - 1
        except (ValueError, AttributeError):
            return self.port

    def monitor_heartbeat(self) -> None:
        """
        Monitor leader heartbeat and trigger a new election on timeout.

        Note:
            Followers check for leader inactivity. If heartbeat exceeds the timeout
            threshold, an election is initiated.

        :return: None
        """
        while True:
            time.sleep(5)
            if self.role == "leader":
                continue
            now = time.time()
            if self.leader_id and now - self.last_heartbeat.get(self.leader_id, 0) > 10:
                console.log(f"[{self.node_id}] Leader {self.leader_id} timeout, starting election.")
                self.start_election()

    def start_election(self) -> None:
        """
        Start a new leader election.

        Note:
            The node becomes a candidate, increments its epoch, votes for itself,
            queries all peers for their votes, and becomes leader if it obtains
            a majority.

        :return: None
        """
        self.role = "candidate"
        self.epoch += 1
        self.election.voted_for = self.node_id
        self.leader_id = None
        console.log(f"[{self.node_id}] Starting election (epoch={self.epoch})")

        my_info = zookeeper_pb2.Election(candidate_id=self.node_id, epoch=self.epoch, seq=self.seq)
        votes = {self.node_id}
        for peer_port in self.peers:
            try:
                with grpc.insecure_channel(f"localhost:{peer_port}") as ch:
                    stub = zookeeper_pb2_grpc.NodeServiceStub(ch)
                    resp = stub.StartElection(my_info)
                    if resp.vote_for == self.node_id:
                        votes.add(f"Node{peer_port - self.base_port + 1}")
            except grpc.RpcError:
                # follower unreachable / RPC failure → skip
                continue

        if len(votes) >= (len(self.peers) + 1) // 2 + 1:
            self.become_leader()
        else:
            console.log(f"[{self.node_id}] Election failed, votes={votes}")

    def start(self) -> None:
        """
        Start the gRPC server for this node.

        Note:
            Registers both NodeService and ClientService, launches heartbeat
            monitoring, and triggers a delayed election for Node1 if no leader
            is present at startup.

        :return: None
        """
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        zookeeper_pb2_grpc.add_NodeServiceServicer_to_server(self, server)
        zookeeper_pb2_grpc.add_ClientServiceServicer_to_server(self, server)
        server.add_insecure_port(f"[::]:{self.port}")
        server.start()

        console.log(f"[START] Node {self.node_id} listening on port {self.port}")
        threading.Thread(target=self.monitor_heartbeat, daemon=True).start()

        if self.node_id == "Node1" and not self.leader_id:
            def delayed_election():
                time.sleep(3)
                console.log(f"[{self.node_id}] No leader detected at startup, starting election.")
                self.start_election()

            threading.Thread(target=delayed_election, daemon=True).start()

        server.wait_for_termination()


def serve(
        node_id: str,
        port: int,
        peers: list[int],
        base_port: int,
) -> None:
    """
    Launch a node server instance.

    Note:
        This function is invoked by ``scripts.run_nodes`` to start each node.

    :param node_id: Identifier of the node.
    :param port: Listening port of the node.
    :param peers: List of peer ports.
    :param base_port: Base port for deriving node ports.
    :return: None
    """
    node = NodeServer(node_id=node_id, port=port, peers=peers, base_port=base_port)
    node.start()
