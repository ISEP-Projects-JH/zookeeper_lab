"""
Exports ``LeaderCoordinator``, the component responsible for leader heartbeat
broadcasting and tracking active follower nodes.
"""

from __future__ import annotations

import grpc
import time
import threading
from rich.console import Console
from zk import zookeeper_pb2, zookeeper_pb2_grpc

__all__ = ["LeaderCoordinator"]


console = Console()


class LeaderCoordinator:
    def __init__(
        self,
        node_id: str,
        base_port: int,
        peers: list[int],
        write_nodes_callback,
    ):
        """
        Initialize the coordinator responsible for leader heartbeat broadcast
        and active-node maintenance.

        :param node_id: ID of the leader node.
        :param base_port: Base port used to calculate node ports.
        :param peers: Ports of follower nodes.
        :param write_nodes_callback: Callback used to update the config file.
        """
        self.node_id: str = node_id
        self.base_port: int = base_port
        self.peers: list[int] = peers
        self.write_nodes_callback = write_nodes_callback

        self.active_nodes: dict[str, int] = {node_id: self.get_port_by_id(node_id)}
        self.last_heartbeat: dict[str, float] = {node_id: time.time()}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def make_heartbeat(self) -> zookeeper_pb2.Heartbeat:
        """
        Construct a standard heartbeat message.

        :return: A Heartbeat protobuf message.
        """
        return zookeeper_pb2.Heartbeat(
            leader_id=self.node_id,
            timestamp=int(time.time()),
        )

    def start(self):
        """
        Start the leader heartbeat-broadcast thread.

        :return: None
        """
        if self._thread and self._thread.is_alive():
            return
        console.log(f"[{self.node_id}] LeaderCoordinator started, broadcasting heartbeats.")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """
        Stop the heartbeat-broadcast thread.

        :return: None
        """
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
        console.log(f"[{self.node_id}] LeaderCoordinator stopped.")

    def _heartbeat_loop(self):
        """
        Periodically:
        - broadcast heartbeats to followers;
        - process reverse heartbeats;
        - update active node list;
        - remove inactive followers;
        - notify the config writer callback.

        :return: None
        """
        while not self._stop_event.is_set():
            now : float
            hb = self.make_heartbeat()

            # Broadcast heartbeat to all peers
            for peer_port in self.peers:
                peer_id = f"Node{peer_port - self.base_port + 1}"
                try:
                    with grpc.insecure_channel(f"localhost:{peer_port}") as ch:
                        stub = zookeeper_pb2_grpc.NodeServiceStub(ch)
                        stub.SendHeartbeat(hb)
                        self.active_nodes[peer_id] = peer_port
                        self.last_heartbeat[peer_id] = time.time()
                except grpc.RpcError:
                    console.log(f"[{self.node_id}] Peer {peer_id} ({peer_port}) unreachable")

            # Update self status
            self.active_nodes[self.node_id] = self.get_port_by_id(self.node_id)
            self.last_heartbeat[self.node_id] = time.time()

            # Remove inactive followers
            now = time.time()
            dead_nodes = [
                nid for nid, ts in self.last_heartbeat.items()
                if nid != self.node_id and now - ts > 10
            ]
            for nid in dead_nodes:
                if nid in self.active_nodes:
                    console.log(f"[{self.node_id}] Removed inactive node {nid}")
                    del self.active_nodes[nid]
                    del self.last_heartbeat[nid]

            # Update config
            try:
                self.write_nodes_callback(self.active_nodes)
            except (PermissionError, FileNotFoundError, IsADirectoryError, OSError) as e:
                console.log(f"[{self.node_id}] Failed to update nodes config: {e}")

            time.sleep(3)

    # ----------------------------------------------------------------------
    # Utility
    # ----------------------------------------------------------------------
    def get_port_by_id(self, node_id: str) -> int:
        """
        Convert NodeX → port value using base_port.

        :param node_id: Node identifier (e.g., "Node1").
        :return: Corresponding port.
        """
        try:
            idx = int(node_id.replace("Node", ""))
            return self.base_port + idx - 1
        except (ValueError, AttributeError):
            return self.base_port
