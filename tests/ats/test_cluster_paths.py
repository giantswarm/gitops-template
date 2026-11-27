"""Pins the `spec.path` of every workload cluster Kustomization, the layout of
docs/reference/repo-structure.md; needs no cluster."""

from pathlib import Path

import yaml
from kind_config import require_example
from repository_gates import WORKLOAD_CLUSTERS_DIR

# the directory each Kustomization applies, relative to the organisation's workload-clusters/:
#  the cluster's applies `cluster/`, the apps one the cluster root, a -direct one `out-of-band/`
EXPECTED_PATHS = {
    "HELLO_APP_DEV_CLUSTER_1.yaml": "HELLO_APP_DEV_CLUSTER_1",
    "HELLO_APP_PROD_CLUSTER_EU_CENTRAL.yaml": "HELLO_APP_PROD_CLUSTER_EU_CENTRAL",
    "HELLO_APP_PROD_CLUSTER_US_WEST.yaml": "HELLO_APP_PROD_CLUSTER_US_WEST",
    "HELLO_APP_STAGING_CLUSTER_1.yaml": "HELLO_APP_STAGING_CLUSTER_1",
    "WC_NAME.yaml": "WC_NAME/cluster",
    "WC_NAME-apps.yaml": "WC_NAME",
    "WC_NAME_OUT_OF_BAND_FLUX_APP.yaml": "WC_NAME_OUT_OF_BAND_FLUX_APP/cluster",
    "WC_NAME_OUT_OF_BAND_FLUX_APP-apps.yaml": "WC_NAME_OUT_OF_BAND_FLUX_APP",
    "WC_NAME_OUT_OF_BAND_NO_FLUX_APP.yaml": "WC_NAME_OUT_OF_BAND_NO_FLUX_APP/cluster",
    "WC_NAME_OUT_OF_BAND_NO_FLUX_APP-apps.yaml": "WC_NAME_OUT_OF_BAND_NO_FLUX_APP",
    "WC_NAME_OUT_OF_BAND_NO_FLUX_APP-direct.yaml": "WC_NAME_OUT_OF_BAND_NO_FLUX_APP/out-of-band",
    "WC_NAME_SCHEDULED_UPGRADES.yaml": "WC_NAME_SCHEDULED_UPGRADES",
    "WC_NAME_IMAGE_AUTOMATION.yaml": "WC_NAME_IMAGE_AUTOMATION",
    "WC_NAME_IMAGE_AUTOMATION-direct.yaml": "WC_NAME_IMAGE_AUTOMATION/out-of-band",
}
PREFIX = "./management-clusters/MC_NAME/organizations/ORG_NAME/workload-clusters/"


def _kustomization_paths(directory: Path) -> dict[str, str]:
    paths = {}
    for file in sorted(directory.glob("*.yaml")):
        if file.name != "kustomization.yaml":
            with file.open() as f:
                paths[file.name] = yaml.safe_load(f)["spec"]["path"]
    return paths


def test_cluster_kustomization_paths() -> None:
    require_example("organisation")
    assert _kustomization_paths(WORKLOAD_CLUSTERS_DIR) == {
        file: PREFIX + path for file, path in EXPECTED_PATHS.items()
    }


def test_cluster_roots_leave_out_cluster_and_out_of_band() -> None:
    require_example("organisation")
    # without a kustomization.yaml, Flux would apply every directory below the cluster
    #  root, out-of-band/ too, to the management cluster
    for path in {path for path in EXPECTED_PATHS.values() if "/" not in path}:
        with (WORKLOAD_CLUSTERS_DIR / path / "kustomization.yaml").open() as f:
            resources = yaml.safe_load(f)["resources"]
        assert "out-of-band/" not in resources, path
        if (WORKLOAD_CLUSTERS_DIR / path / "apps").is_dir():
            assert "cluster/" not in resources, path
