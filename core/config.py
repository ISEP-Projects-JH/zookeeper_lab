"""
Exports ``config_path``, the resolved absolute path to ``config/nodes.txt``.
"""

from pathlib import Path

__all__ = ["config_path"]

current_file: Path = Path(__file__).resolve()
project_root: Path = current_file.parent.parent

# Primary exported entity: absolute path to config/nodes.txt
config_path: Path = project_root / "config" / "nodes.txt"
