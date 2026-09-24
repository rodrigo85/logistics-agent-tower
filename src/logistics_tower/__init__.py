"""
Logistics Agent Tower - autonomous multi-agent dispatch and routing control tower.

Built with LangGraph (orchestration + Human-in-the-Loop), Google OR-Tools (CVRPTW),
Model Context Protocol (tool boundary), FastAPI (API + dashboard) and SQLAlchemy 2.0.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("logistics-agent-tower")
except PackageNotFoundError:  # pragma: no cover - running from a raw checkout without install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
