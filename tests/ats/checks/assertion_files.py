"""The assertion files: the objects the clusters have to have."""

import logging
import os
from pathlib import Path

import yaml

ASSERTIONS_DIR = Path("assertions")
EXISTS_ASSERTIONS_DIR = str(ASSERTIONS_DIR / "exists")
# objects expected in the workload cluster the test's vCluster stands in for
WORKLOAD_CLUSTER_ASSERTIONS_DIR = str(ASSERTIONS_DIR / "exists-in-workload-cluster")

logger = logging.getLogger(__name__)


def load_assertions(
    assertions_dir: str = EXISTS_ASSERTIONS_DIR,
) -> dict[str, list[dict]]:
    """The objects in each `.yaml` file under `assertions_dir`, by file."""
    assertions = {}
    for dir_path, _, filenames in os.walk(assertions_dir):
        for file in filenames:
            path = Path(dir_path) / file
            if path.suffix != ".yaml":
                logger.debug(
                    f"Ignoring file '{path}' in '{assertions_dir}' as it's not a file or it"
                    f" doesn't have a '.yaml' extension."
                )
                continue
            with path.open() as f:
                assertions[str(path)] = [d for d in yaml.safe_load_all(f) if d]
    return assertions


def all_assertions(assertions: dict[str, list[dict]]) -> list[dict]:
    """The assertions of every file, in one list."""
    return [a for file_assertions in assertions.values() for a in file_assertions]
