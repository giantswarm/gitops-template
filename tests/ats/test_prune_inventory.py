"""Checks of how test_prune reads a Kustomization's inventory and drops objects from what it
builds; they need no cluster."""

import yaml
from flux_inventory import applied_deployments, inventory_keys, left_out_problems
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


def test_delete_patches_without_substitution() -> None:
    # P4: the management cluster's Kustomization substitutes nothing, so its patches name the
    #  objects as they are
    patches = delete_patches(
        [("Kustomization", "default", "mc-name-organization-org-name")], {}
    )
    assert yaml.safe_load(patches[0]["patch"])["metadata"] == {
        "name": "mc-name-organization-org-name",
        "namespace": "default",
    }


NAMESPACE_KUSTOMIZATION = ("Kustomization", "default", "mc-name-organization-org-name")


def root(ready: str, generation: int, observed: int, ids: list[str]) -> dict:
    return {
        "metadata": {
            "name": "mc-name-gitops",
            "namespace": "default",
            "generation": generation,
        },
        "status": {
            "observedGeneration": observed,
            "conditions": [{"type": "Ready", "status": ready, "reason": "Reason"}],
            "inventory": {"entries": [{"id": i, "v": "v1"} for i in ids]},
        },
    }


def test_left_out_problems() -> None:
    listed = [
        "default_mc-name-organization-org-name_kustomize.toolkit.fluxcd.io_Kustomization"
    ]
    assert left_out_problems(root("True", 2, 2, []), NAMESPACE_KUSTOMIZATION) == []
    assert left_out_problems(root("True", 2, 1, []), NAMESPACE_KUSTOMIZATION) == [
        "Kustomization 'default/mc-name-gitops' hasn't applied its spec yet"
    ]
    assert left_out_problems(root("False", 2, 2, []), NAMESPACE_KUSTOMIZATION) == [
        "Kustomization 'default/mc-name-gitops' isn't Ready: Reason"
    ]
    assert left_out_problems(root("True", 2, 2, listed), NAMESPACE_KUSTOMIZATION) == [
        "Kustomization 'default/mc-name-gitops' still lists "
        "('Kustomization', 'default', 'mc-name-organization-org-name')"
    ]


def test_delete_patches_drop_an_application_team() -> None:
    # the team's GitRepository and Kustomization, which test_prune removes from the apps
    #  Kustomization before it deletes the cluster, as the getting-started guides do
    patches = delete_patches(
        [
            ("GitRepository", "org-org-name", "out-of-band-no-flux-hello-team"),
            ("Kustomization", "org-org-name", "out-of-band-no-flux-hello-team"),
        ]
    )
    assert [yaml.safe_load(p["patch"])["apiVersion"] for p in patches] == [
        "source.toolkit.fluxcd.io/v1",
        "kustomize.toolkit.fluxcd.io/v1",
    ]


def test_applied_deployments_leaves_out_releases_other_kustomizations_applied() -> None:
    # a ResourceSet of the organization installs an app into the cluster, too
    ours = {
        "helmRelease": "org-org-name/wc-app",
        "kind": "Deployment",
        "metadata": {"name": "app", "namespace": "app"},
    }
    theirs = {
        "helmRelease": "org-org-name/wc-scheduled",
        "kind": "Deployment",
        "metadata": {"name": "scheduled", "namespace": "scheduled"},
    }
    crd = {
        "helmRelease": "org-org-name/wc-app",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": "gateways.gateway.networking.k8s.io"},
    }
    applied = {("HelmRelease", "org-org-name", "wc-app")}
    assert applied_deployments([ours, theirs, crd], applied) == [ours]
