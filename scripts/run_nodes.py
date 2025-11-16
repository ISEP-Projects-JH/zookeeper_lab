# scripts/run_nodes.py
import sys
from pathlib import Path

import click
import multiprocessing
from core.node_server import serve

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))


@click.command()
@click.option("--count", default=5, help="Number of nodes to launch")
@click.option("--base-port", default=50050, help="Starting port number")
def run_nodes(count, base_port):
    """
    Example:
        python scripts/run_nodes.py --count 3 --base-port 50050
    """
    processes = []
    ports = [base_port + i for i in range(count)]

    for i in range(count):
        peers = [p for p in ports if p != ports[i]]
        node_id = f"Node{i + 1}"

        p = multiprocessing.Process(target=serve, args=(node_id, ports[i], peers, base_port))
        p.start()
        processes.append(p)
        print(f"[INIT] Started {node_id} on port {ports[i]} with peers {peers}")

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        print("\nStopping all nodes...")
        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join()
        print("All nodes stopped.")


if __name__ == "__main__":
    run_nodes()
