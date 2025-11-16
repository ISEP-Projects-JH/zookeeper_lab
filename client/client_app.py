import time
import grpc
from typing import List, Optional, Tuple, cast

from core.config import config_path
from zk import zookeeper_pb2, zookeeper_pb2_grpc


class ZookeeperClientShell:
    """
    Interactive shell for communicating with the simulated ZooKeeper-like cluster.

    Note:
        This client supports connecting to cluster nodes, sending write/guess/read
        requests, and reading configuration metadata. It does not implement any
        replication or consensus logic; it only interacts with the server nodes
        that expose the gRPC ClientService API.

    Usage:
        Create an instance and call ``run()`` to start the shell loop.
    """

    def __init__(self):
        self.channel = None
        self.stub = None
        self.prompt = "zookeeper> "

    # ------------------------------------------------
    def run(self) -> None:
        """
        Start the interactive command shell.

        Note:
            This method enters a blocking REPL loop. Commands include:
            ``connect``, ``nodes``, ``write``, ``guess``, ``read``, ``help``, and ``exit``.

        Details:
            This method continuously accepts user input, parses commands,
            and dispatches them to the appropriate handlers. It does not return
            until the user quits.

        :return: None
        """
        print("ZooKeeper-like Client Shell")
        print("Type 'help' for commands.")
        while True:
            try:
                line = input(self.prompt).strip()
            except EOFError:
                print("\nBye.")
                break

            if not line:
                print("Not a valid command.")
                print("Type 'help' for commands.")
                continue

            parts = line.split()
            cmd = parts[0].lower()

            if cmd in ("exit", "quit"):
                print("Bye.")
                break

            elif cmd == "help":
                self.print_help()

            elif cmd == "nodes":
                self.list_nodes()

            elif cmd == "connect":
                if len(parts) == 1:
                    node = self.get_leader()
                    if not node:
                        print("No leader found in config.")
                        continue
                    host, port = "localhost", node[2]
                    self.connect(host, port)
                elif len(parts) == 3:
                    host, port = parts[1], parts[2]
                    self.connect(host, port)
                else:
                    print("Usage: connect [<host> <port>] or connect (auto)")
                    continue

            elif cmd in ("write", "guess", "read"):
                if not self.stub:
                    print("Not connected. Use 'connect' first.")
                    continue
                self.handle_request(cmd, parts)

            else:
                print(f"Unknown command: {cmd}")

    @staticmethod
    def print_help() -> None:
        """
        Start the interactive command shell.

        Note:
            This method enters a blocking REPL loop. Commands include:
            ``connect``, ``nodes``, ``write``, ``guess``, ``read``, ``help``, and ``exit``.

        Details:
            This method continuously accepts user input, parses commands,
            and dispatches them to the appropriate handlers. It does not return
            until the user quits.

        :return: None
        """
        print("""
Commands:
  nodes                  Show current nodes (from config)
  connect                Auto-connect to current leader
  connect <host> <port>  Connect manually
  write <num>            Set a new target value (0–100)
  guess <num>            Submit a guess
  read                   Read current committed value [DEBUG ONLY]
  exit                   Quit shell
""")

    def connect(self, host: str, port: str) -> None:
        """
        Connect to a server node and create a gRPC stub.

        Note:
            This method ensures the server is reachable by waiting for
            the channel to become ready. If the connection fails, the stub
            is cleared and an error message is printed.

        :param host: Hostname or IP of the target node.
        :param port: Port number of the target node.
        :return: None
        """
        try:
            self.channel = grpc.insecure_channel(f"{host}:{port}")
            grpc.channel_ready_future(self.channel).result(timeout=2)
            self.stub = zookeeper_pb2_grpc.ClientServiceStub(self.channel)
            print(f"✅ Connected to {host}:{port}")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            self.stub = None
            self.channel = None
            print("Please try 'connect' again once a node is available.")

    def list_nodes(self) -> None:
        """
        Display current cluster nodes, retrying up to three times.

        Note:
            Node information is loaded from ``config/nodes.txt``. If the file
            is temporarily unavailable or empty, a retry loop is attempted.

        :return: None
        """
        for attempt in range(3):
            nodes = self._read_nodes()
            if nodes:
                print("Current cluster nodes:")
                for role, nid, port in nodes:
                    tag = "⭐" if role == "leader" else " "
                    print(f" {tag} {role:<8} {nid:<8} port={port}")
                return
            print(f"(Attempt {attempt + 1}/3) No nodes found, retrying...")
            time.sleep(1)
        print("⚠️  Temporarily no active nodes found.")

    @staticmethod
    def _read_nodes() -> List[Tuple[str, str, str]]:
        """
        Read node metadata from configuration.

        Note:
            This reads ``config/nodes.txt`` and returns all non-comment,
            non-empty lines. If parsing fails, an empty list is returned.

        :return: A list of tuples ``(role, node_id, port)``.
        """
        try:
            if not config_path.exists():
                return []
            lines = [l.strip() for l in config_path.read_text().splitlines()
                     if l.strip() and not l.startswith("#")]
            nodes = [cast(tuple[str, str, str], tuple(l.split())) for l in lines]
            return nodes
        except Exception as e:
            print(f"Error reading config: {e}")
            return []

    def get_leader(self) -> Optional[Tuple[str, str, str]]:
        """
        Retrieve the current leader node from configuration.

        :return: A tuple ``(role, node_id, port)`` if a leader exists, otherwise ``None``.
        """
        nodes = self._read_nodes()
        for role, nid, port in nodes:
            if role == "leader":
                return role, nid, port
        return None

    def handle_request(self, cmd: str, parts: List[str]) -> None:
        """
        Dispatch a request to the connected server node.

        Note:
            Supports ``write``, ``guess``, and ``read``. This method also checks
            whether the gRPC channel is still alive before sending the request.

        :param cmd: Command keyword ('write', 'guess', or 'read').
        :param parts: Full command split into tokens.
        :return: None
        """
        if not self.stub:
            print("⚠️  Not connected. Use 'connect' first.")
            return

        # ensure channel still available
        try:
            grpc.channel_ready_future(self.channel).result(timeout=1)
        except (grpc.RpcError, grpc.FutureTimeoutError):
            print("⚠️  Lost connection to node. Please reconnect.")
            self.stub = None
            self.channel = None
            return

        # Construct request
        if cmd == "write" and len(parts) == 2:
            val = parts[1]
            req = zookeeper_pb2.ClientRequest(op=zookeeper_pb2.WRITE, value=val)
        elif cmd == "guess" and len(parts) == 2:
            val = parts[1]
            req = zookeeper_pb2.ClientRequest(op=zookeeper_pb2.GUESS, value=val)
        elif cmd == "read":
            req = zookeeper_pb2.ClientRequest(op=zookeeper_pb2.UNKNOWN, value="")
        else:
            print("Invalid command or missing value.")
            return

        # Send RPC
        try:
            resp = self.stub.SubmitRequest(req)
            msg = resp.message or "(no message)"
            print(f"[Server] {msg}")
            if resp.current_target:
                print(f"[Target] {resp.current_target}")
        except Exception as e:
            print(f"❌ RPC error: {e}")
            print("💡 The node may be down. Try 'connect' again.")
            self.stub = None
            self.channel = None


def main() -> None:
    """
    Entry point for launching the command shell.

    :return: None
    """
    shell = ZookeeperClientShell()
    shell.run()


if __name__ == "__main__":
    main()
