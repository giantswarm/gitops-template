"""The CRD copies workload_cluster_flux_crds creates in the test's workload cluster; needs no
cluster."""

from workload_cluster_flux_crds import crd_copy


def test_crd_copy_drops_what_the_cluster_set() -> None:
    crd = {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {
            "name": "kustomizations.kustomize.toolkit.fluxcd.io",
            "resourceVersion": "42",
            "uid": "u",
            "managedFields": [{}],
        },
        "spec": {"group": "kustomize.toolkit.fluxcd.io"},
        "status": {"conditions": []},
    }
    assert crd_copy(crd) == {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": "kustomizations.kustomize.toolkit.fluxcd.io"},
        "spec": {"group": "kustomize.toolkit.fluxcd.io"},
    }
