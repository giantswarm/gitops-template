"""Checks of how test_prune reads a Kustomization's inventory and drops objects from what it
builds; they need no cluster."""

import yaml
from flux_inventory import inventory_keys
from prune_patches import delete_patches


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


def test_inventory_keys_of_a_name_with_a_colon() -> None:
    # Flux writes a colon in a name, as RBAC objects often have, as `__`
    kustomization = {
        "status": {
            "inventory": {
                "entries": [
                    {
                        "id": "_kyverno__generate-configmaps_rbac.authorization.k8s.io_ClusterRole",
                        "v": "v1",
                    },
                ]
            }
        }
    }
    assert inventory_keys(kustomization) == {
        ("ClusterRole", "", "kyverno:generate-configmaps"),
    }


def test_inventory_keys_of_a_kustomization_without_inventory() -> None:
    assert inventory_keys({"status": {}}) == set()


def test_delete_patches_name_the_objects_before_substitution() -> None:
    patches = delete_patches(
        [("HelmRelease", "org-org-name", "out-of-band-no-flux-hello-world")]
    )
    assert [yaml.safe_load(p["patch"]) for p in patches] == [
        {
            "$patch": "delete",
            "apiVersion": "helm.toolkit.fluxcd.io/v2",
            "kind": "HelmRelease",
            "metadata": {
                "name": "${cluster_name}-hello-world",
                "namespace": "org-${organization}",
            },
        }
    ]
