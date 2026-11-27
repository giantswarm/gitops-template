"""One object, one Flux Kustomization: no object is applied to the same cluster by two of them,
see docs/explanation/one-owner.md. Checks of one_owner on small repositories, and of every
management cluster the kind test applies; they need no cluster, only kubectl."""

import warnings
from pathlib import Path

import pytest
import yaml
from flux_builds import Applied, Owner
from kind_config import RootKustomization, kind_test_config
from one_owner import Identity, identity, owned_objects, shared_objects
from root_build import REPO_DIR

ROOT_FILE = Path("management-clusters/mc/mc.yaml")
REPOSITORY = "your-repo"
ORG_NAMESPACE = "org-acme"
CLUSTERS = "management-clusters/mc/clusters"


def write(repo: Path, files: dict[str, list[dict]]) -> None:
    for name, docs in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump_all(docs))


def kustomization(name: str, path: str, **spec: object) -> dict:
    return {
        "apiVersion": "kustomize.toolkit.fluxcd.io/v1",
        "kind": "Kustomization",
        "metadata": {"name": name, "namespace": "default"},
        "spec": {
            "path": path,
            "sourceRef": {"kind": "GitRepository", "name": REPOSITORY},
            **spec,
        },
    }


def config_map(name: str, namespace: str | None = None, **data: str) -> dict:
    metadata = {"name": name} | ({"namespace": namespace} if namespace else {})
    return {"apiVersion": "v1", "kind": "ConfigMap", "metadata": metadata, "data": data}


def cluster_kustomization(cluster: str, path: str, **spec: object) -> dict:
    """A workload cluster's Kustomization, applying into the organisation's namespace with the
    cluster's name."""
    return kustomization(
        f"mc-clusters-{cluster}",
        path,
        targetNamespace=ORG_NAMESPACE,
        postBuild={"substitute": {"cluster_name": cluster}},
        **spec,
    )


def repository(
    tmp_path: Path, clusters: list[dict], files: dict[str, list[dict]]
) -> Path:
    """A repository whose root applies `clusters`, one file each, and `files`."""
    write(
        tmp_path,
        {
            str(ROOT_FILE): [kustomization("mc-gitops", "./management-clusters/mc")],
            **{f"{CLUSTERS}/{k['metadata']['name']}.yaml": [k] for k in clusters},
            **files,
        },
    )
    return tmp_path


def findings(repo: Path) -> list[str]:
    owned, _ = owned_objects(repo, ROOT_FILE)
    return shared_objects(owned)


def test_a_base_for_two_clusters_named_after_the_cluster(tmp_path: Path) -> None:
    repo = repository(
        tmp_path,
        [cluster_kustomization(c, "./bases/app") for c in ("a", "b")],
        {"bases/app/values.yaml": [config_map("${cluster_name}-values")]},
    )
    assert findings(repo) == []


def test_a_base_for_two_clusters_in_one_namespace(tmp_path: Path) -> None:
    repo = repository(
        tmp_path,
        [cluster_kustomization(c, "./bases/app") for c in ("a", "b")],
        {"bases/app/values.yaml": [config_map("app-values")]},
    )
    assert findings(repo) == [
        f"ConfigMap '{ORG_NAMESPACE}/app-values' on the management cluster is applied by:\n"
        f"  - Kustomization 'default/mc-clusters-a', in {CLUSTERS}/mc-clusters-a.yaml, "
        "spec.path bases/app\n"
        f"  - Kustomization 'default/mc-clusters-b', in {CLUSTERS}/mc-clusters-b.yaml, "
        "spec.path bases/app"
    ]


def test_a_kustomization_in_two_builds(tmp_path: Path) -> None:
    shared = kustomization("shared", "./apps/shared")
    listing = {"resources": ["../shared/kustomization-shared.yaml"]}
    repo = repository(
        tmp_path,
        [
            kustomization("first", "./apps/first"),
            kustomization("second", "./apps/second"),
        ],
        {
            "apps/shared/kustomization-shared.yaml": [shared],
            "apps/shared/values.yaml": [config_map("shared", "default")],
            "apps/first/kustomization.yaml": [listing],
            "apps/second/kustomization.yaml": [listing],
        },
    )
    problems = findings(repo)
    assert len(problems) == 1
    assert problems[0].startswith(
        "Kustomization.kustomize.toolkit.fluxcd.io 'default/shared' on the management cluster"
    )
    assert "'default/first'" in problems[0]
    assert "'default/second'" in problems[0]


def resource_set(name: str, resources: list[dict], **spec: object) -> dict:
    return {
        "apiVersion": "fluxcd.controlplane.io/v1",
        "kind": "ResourceSet",
        "metadata": {"name": name, "namespace": ORG_NAMESPACE},
        "spec": {"resources": resources, **spec},
    }


def helm_release(name: str, namespace: str, **spec: object) -> dict:
    return {
        "apiVersion": "helm.toolkit.fluxcd.io/v2",
        "kind": "HelmRelease",
        "metadata": {"name": name, "namespace": namespace},
        "spec": spec,
    }


PROVIDER_NAMESPACE = "<< inputs.provider.namespace >>"


@pytest.mark.parametrize(
    ("name", "spec"),
    [
        # Flatten, the default: each entry of `inputs` is `inputs`
        ("<< inputs.cluster >>-app", {}),
        # Permute: the ResourceSet's own entries are under its name, `-` as `_`
        ("<< inputs.app_set.cluster >>-app", {"inputStrategy": {"name": "Permute"}}),
    ],
)
def test_a_resource_set_and_a_manifest(tmp_path: Path, name: str, spec: dict) -> None:
    rendered = helm_release(name, PROVIDER_NAMESPACE)
    repo = repository(
        tmp_path,
        [
            cluster_kustomization("a", "./apps/a"),
            kustomization(
                "multicluster", "./apps/multicluster", targetNamespace=ORG_NAMESPACE
            ),
        ],
        {
            "apps/a/app.yaml": [helm_release("${cluster_name}-app", ORG_NAMESPACE)],
            "apps/multicluster/app.yaml": [
                resource_set("app-set", [rendered], inputs=[{"cluster": "a"}], **spec)
            ],
        },
    )
    problems = findings(repo)
    assert len(problems) == 1
    assert problems[0].startswith(
        f"HelmRelease.helm.toolkit.fluxcd.io '{ORG_NAMESPACE}/a-app' on the management cluster"
    )
    assert "Kustomization 'default/mc-clusters-a'" in problems[0]
    assert (
        f"ResourceSet '{ORG_NAMESPACE}/app-set', in apps/multicluster/app.yaml, applied by "
        "Kustomization 'default/multicluster'"
    ) in problems[0]


def test_a_resource_set_input_from_a_provider_is_not_checked(tmp_path: Path) -> None:
    rendered = helm_release("<< inputs.tag >>-app", PROVIDER_NAMESPACE)
    repo = repository(
        tmp_path,
        [
            kustomization(
                "multicluster", "./apps/multicluster", targetNamespace=ORG_NAMESPACE
            )
        ],
        {"apps/multicluster/app.yaml": [resource_set("app-set", [rendered])]},
    )
    owned, unchecked = owned_objects(repo, ROOT_FILE)
    assert shared_objects(owned) == []
    assert unchecked == [
        f"ResourceSet '{ORG_NAMESPACE}/app-set': HelmRelease '<< inputs.tag >>-app' has an "
        "input only Flux Operator fills in"
    ]


OUT_OF_BAND = "./workload-clusters/a/out-of-band"
KUBECONFIG = {"secretRef": {"name": "a-kubeconfig"}}


def out_of_band(
    tmp_path: Path, clusters: list[dict], files: dict | None = None
) -> Path:
    return repository(
        tmp_path,
        clusters,
        {f"{OUT_OF_BAND.removeprefix('./')}/values.yaml": [config_map("wc", "default")]}
        | (files or {}),
    )


def direct(name: str = "mc-clusters-a-direct") -> dict:
    return kustomization(name, OUT_OF_BAND, kubeConfig=KUBECONFIG)


def test_out_of_band_on_the_management_cluster_and_the_workload_cluster(
    tmp_path: Path,
) -> None:
    # The cluster's Kustomization puts out-of-band/ on the management cluster, which is a
    # mistake of its own, but not two owners of one object: the -direct one's are in the
    # workload cluster.
    repo = out_of_band(
        tmp_path, [kustomization("mc-clusters-a", OUT_OF_BAND), direct()]
    )
    assert findings(repo) == []


def test_out_of_band_by_two_direct_kustomizations(tmp_path: Path) -> None:
    repo = out_of_band(tmp_path, [direct(), direct("mc-clusters-a-direct-2")])
    problems = findings(repo)
    assert len(problems) == 1
    assert problems[0].startswith(
        "ConfigMap 'default/wc' on the cluster of the kubeconfig Secret "
        "'default/a-kubeconfig' is applied by:"
    )


FLUX_APP_VALUES = {
    "kustomizations": [{"name": "out-of-band", "path": OUT_OF_BAND}],
}


def flux_app(values_from: list[dict] | None = None, **spec: object) -> list[dict]:
    """flux-app installed into the cluster `a`, and its chart."""
    chart = {
        "apiVersion": "source.toolkit.fluxcd.io/v1",
        "kind": "OCIRepository",
        "metadata": {"name": "a-flux", "namespace": "default"},
        "spec": {"url": "oci://gsoci.azurecr.io/charts/giantswarm/flux-app"},
    }
    release = helm_release(
        "a-flux",
        "default",
        chartRef={"kind": "OCIRepository", "name": "a-flux"},
        kubeConfig=KUBECONFIG,
        targetNamespace="flux-app",
        valuesFrom=values_from or [],
        **spec,
    )
    return [chart, release]


def test_out_of_band_by_a_direct_kustomization_and_the_clusters_flux(
    tmp_path: Path,
) -> None:
    values = config_map(
        "a-flux-values", "default", values=yaml.safe_dump(FLUX_APP_VALUES)
    )
    repo = out_of_band(
        tmp_path,
        [direct(), kustomization("mc-clusters-a-apps", "./apps/a")],
        {
            "apps/a/flux.yaml": flux_app(
                [{"kind": "ConfigMap", "name": "a-flux-values", "valuesKey": "values"}]
            ),
            "apps/a/values.yaml": [values],
        },
    )
    problems = findings(repo)
    assert len(problems) == 1
    assert "Kustomization 'default/mc-clusters-a-direct'" in problems[0]
    assert (
        "Kustomization 'flux-app/out-of-band', in apps/a/values.yaml, spec.path "
        "workload-clusters/a/out-of-band, of the workload cluster's Flux that "
        "HelmRelease 'default/a-flux' installs"
    ) in problems[0]


def test_the_clusters_flux_with_inline_values_alone(tmp_path: Path) -> None:
    repo = out_of_band(
        tmp_path,
        [kustomization("mc-clusters-a-apps", "./apps/a")],
        {"apps/a/flux.yaml": flux_app(values=FLUX_APP_VALUES)},
    )
    owned, unchecked = owned_objects(repo, ROOT_FILE)
    assert unchecked == []
    assert shared_objects(owned) == []
    assert any(o.owner and o.owner.name == "out-of-band" for o in owned)


def test_the_clusters_flux_with_a_path_that_is_not_in_the_repository(
    tmp_path: Path,
) -> None:
    values = {"kustomizations": [{"name": "gone", "path": "./gone"}]}
    repo = out_of_band(
        tmp_path,
        [kustomization("mc-clusters-a-apps", "./apps/a")],
        {"apps/a/flux.yaml": flux_app(values=values)},
    )
    _, unchecked = owned_objects(repo, ROOT_FILE)
    assert unchecked == [
        "Kustomization 'flux-app/gone' of the workload cluster's Flux that HelmRelease "
        "'default/a-flux' installs: its spec.path, gone, isn't in this repository"
    ]


def test_identity_leaves_out_the_version_and_the_namespace_of_cluster_scoped_kinds() -> (
    None
):
    owner = Owner("Kustomization", "default", "k", "k.yaml")
    role = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": "r"},
    }
    assert identity(Applied("", "org-acme", role, "p", owner)) == Identity(
        "", "rbac.authorization.k8s.io", "ClusterRole", "", "r"
    )
    secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "s"}}
    assert identity(Applied("ns/kc", "org-acme", secret, "p", owner)) == Identity(
        "ns/kc", "", "Secret", "org-acme", "s"
    )


@pytest.fixture(
    scope="module",
    params=kind_test_config().roots(),
    ids=lambda r: r.management_cluster,
)
def root(request: pytest.FixtureRequest) -> RootKustomization:
    return request.param


def test_no_object_has_two_kustomizations(root: RootKustomization) -> None:
    owned, unchecked = owned_objects(REPO_DIR, root.file)
    for reason in unchecked:
        warnings.warn(f"Not checked for two owners: {reason}", stacklevel=1)
    problems = shared_objects(owned)
    assert not problems, (
        "\n".join(problems)
        + "\n\nEach object needs one owner: list it in one build only. "
        'See docs/explanation/one-owner.md, "The same controller twice".'
    )
