# **ZooKeeper-like Distributed Coordination System**

This project implements a simplified **ZooKeeper-like distributed coordination service** using Python and gRPC.
It supports:

* Leader election
* Log replication
* Majority commit
* Heartbeat monitoring
* Failure recovery
* Stateless clients
* Arbitrary cluster size

This system is designed for educational purposes, demonstrating the core ideas of **ZAB-style consensus**.

---

## **1. Environment Setup**

Create and activate the Conda environment:

```bash
conda env create -f environment.yml
conda activate zookeeper-lab
```

---

## **2. Generate gRPC Sources**

To compile the `.proto` file and generate Python gRPC bindings:

```bash
python -m grpc_tools.protoc \
    --proto_path=./zk \
    --python_out=./zk \
    --grpc_python_out=./zk \
    --pyi_out=./zk \
    ./zk/zookeeper.proto
```

Fix the gRPC import path:

```bash
sed -i.bak 's/^import zookeeper_pb2/from . import zookeeper_pb2/' zk/zookeeper_pb2_grpc.py && rm zk/zookeeper_pb2_grpc.py.bak
```

---

## **3. Run the Server Nodes**

Start the configured cluster (any number of nodes depending on your configuration):

```bash
conda activate zookeeper-lab
python -m scripts.run_nodes
```

Each node runs as its own process and participates in:

* Leader election
* Heartbeat exchange
* Log replication
* Majority commit

---

## **4. Run the Client Application**

Start an interactive client:

```bash
conda activate zookeeper-lab
python -m client.client_app
```

The client supports commands such as:

* `connect <node_id>` — choose a node to send RPC requests
* `write <value>` — submit a write operation
* `guess <value>` — send a guess value (test operation)
* `read` — read the current committed value
* `help` — show available commands

Clients are **stateless** and may connect to any node.
Requests automatically route to the current Leader.

---

## **5. Kill the Leader Node**

To simulate leader failure:

```bash
conda activate zookeeper-lab
python -m scripts.kill_leader
```

The remaining nodes will detect the lost heartbeat and:

* Trigger a new election
* Choose a new Leader
* Restore state from persistent logs
* Continue serving requests

---

## **6. Project Structure**

```
zookeeper_lab/
├── client/            # Stateless client implementation
├── core/              # Node server, leader, election, log store
├── scripts/           # Utility scripts (run nodes, kill leader)
├── zk/                # gRPC .proto and generated code
├── config/            # Cluster configuration
├── environment.yml    # Conda environment definition
└── README.md
```

---

## **7. Notes**

* The cluster size is **configurable**, not fixed to 5 nodes.
* The number of clients is **unlimited**, as clients use stateless gRPC calls.
* This project **does not implement** full application/game logic — only coordination semantics similar to ZooKeeper.
* `read` is provided as a debugging helper because true ZooKeeper does not push values to clients.

## **8. License**

This is a **student project** created solely for academic coursework and demonstration purposes.
No license is provided, and the project is **not intended for production or commercial use**.
