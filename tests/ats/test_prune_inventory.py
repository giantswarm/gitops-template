"""Checks of how test_prune reads a Kustomization's inventory; they need no cluster."""

from flux_inventory import inventory_keys


def test_inventory_keys() -> None:
    # a namespaced object of the core API, a namespaced CR and a cluster-scoped CR
    kustomization = {
        "status": {
            "inventory": {
                "entries": [
                    {"id": "org-org-name_wc-config__ConfigMap", "v": "v1"},
                    {
                        "id": "org-org-name_wc_helm.toolkit.fluxcd.io_HelmRelease",
                        "v": "v2",
                    },
                    {
                        "id": "_org-name_security.giantswarm.io_Organization",
                        "v": "v1alpha1",
                    },
                ]
            }
        }
    }
    assert inventory_keys(kustomization) == {
        ("ConfigMap", "org-org-name", "wc-config"),
        ("HelmRelease", "org-org-name", "wc"),
        ("Organization", "", "org-name"),
    }


def test_inventory_keys_of_a_kustomization_without_inventory() -> None:
    assert inventory_keys({"status": {}}) == set()
