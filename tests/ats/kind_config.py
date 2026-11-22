"""What the kind test needs to know about the repository it tests: tests/ats/kind-test.yaml, and
what it finds in the repository itself.

The test has two parts. The generic part works on whatever is under `management-clusters/`: it
applies the root Kustomization of each management cluster, `<name>/<name>.yaml`, creates the
GitRepository each root reads and the Secret each root decrypts with, stands in for the platform
and waits for everything Flux applies to get Ready. It finds all of that in the repository;
`managementClusters` in kind-test.yaml only narrows which management clusters it applies.

The example part checks the template's examples. Each example check names, in the `examples`
section, the directories of the repository it needs; when one of them isn't there, or belongs to
a management cluster the test doesn't apply, the check is skipped and says why. The other
sections are data that a fork sets for its own clusters: the node pools each cluster has, the
base apps a gated cluster applies before it's Available, and the stand-in secret store. In the
template's own CI, `require_example` fails instead of skipping, so a broken binding can't hide
a check.

docs/reference/ci-checks.md, "Configuration", documents the file.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest
import yaml

REPO_DIR = Path(__file__).resolve().parents[2]
CONFIG_FILE = Path(__file__).resolve().parent / "kind-test.yaml"
MANAGEMENT_CLUSTERS_DIR = "management-clusters"
DEFAULT_NAMESPACE = "default"
# In the template's own CI every example check runs: a skipped one is a broken binding.
TEMPLATE_REPOSITORY = "giantswarm/gitops-template"
KEYS = {"managementClusters", "examples", "nodePools", "clusterBaseApps", "secretStore"}

# (namespace, name)
Ref = tuple[str, str]


class ConfigError(Exception):
    """The repository or kind-test.yaml doesn't say what the test needs to know."""


class UnknownKeysError(ConfigError):
    def __init__(self, file: str, unknown: list[str]) -> None:
        super().__init__(f"{file}: unknown keys {unknown}; the keys are {sorted(KEYS)}")


class NoManagementClusterError(ConfigError):
    def __init__(self) -> None:
        super().__init__(
            f"No management cluster in {MANAGEMENT_CLUSTERS_DIR}/: the test applies each "
            "directory <name> with a <name>/<name>.yaml"
        )


class MissingManagementClustersError(ConfigError):
    def __init__(self, missing: list[str]) -> None:
        files = ", ".join(f"{MANAGEMENT_CLUSTERS_DIR}/{mc}/{mc}.yaml" for mc in missing)
        super().__init__(f"managementClusters names {missing}, but there is no {files}")


class NoRootError(ConfigError):
    def __init__(self, file: Path) -> None:
        super().__init__(
            f"{file} has no Flux Kustomization that applies ./{file.parent}, the "
            "management cluster's root"
        )


class NoExamplePathsError(ConfigError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"examples: the binding of '{name}' needs the paths of the example"
        )


@dataclass(frozen=True)
class RootKustomization:
    """A management cluster's root Kustomization: the one in `<name>/<name>.yaml` that applies
    the management cluster's directory."""

    management_cluster: str
    # relative to the repository
    file: Path
    name: str
    namespace: str
    git_repository: Ref | None
    decryption_secret: Ref | None


def load_config(path: Path = CONFIG_FILE) -> dict:
    """The settings in `path`, or none when there's no file. Fail on a key the test doesn't
    know, rather than ignore a misspelled one."""
    if not path.is_file():
        return {}
    with path.open() as f:
        settings = yaml.safe_load(f) or {}
    unknown = sorted(set(settings) - KEYS)
    if unknown:
        raise UnknownKeysError(path.name, unknown)
    return settings


def management_clusters(repo_dir: Path, configured: list[str] | None) -> list[str]:
    """The management clusters the test applies: the `configured` ones, or every directory
    `management-clusters/<name>` with a `<name>.yaml`."""
    top = repo_dir / MANAGEMENT_CLUSTERS_DIR
    found = sorted(
        d.name for d in top.iterdir() if d.is_dir() and (d / f"{d.name}.yaml").is_file()
    )
    if configured is None:
        if not found:
            raise NoManagementClusterError
        return found
    missing = [mc for mc in configured if mc not in found]
    if missing:
        raise MissingManagementClustersError(missing)
    return list(configured)


def _ref(spec: dict, namespace: str, kind: str | None = None) -> Ref | None:
    if not spec.get("name") or (kind and spec.get("kind") != kind):
        return None
    return (spec.get("namespace", namespace), spec["name"])


def root_kustomization(repo_dir: Path, mc: str) -> RootKustomization:
    """The root Kustomization of the management cluster `mc`."""
    file = Path(MANAGEMENT_CLUSTERS_DIR) / mc / f"{mc}.yaml"
    with (repo_dir / file).open() as f:
        docs = [d for d in yaml.safe_load_all(f) if isinstance(d, dict)]
    for doc in docs:
        spec = doc.get("spec") or {}
        path = str(spec.get("path", "")).removeprefix("./").rstrip("/")
        if doc.get("kind") != "Kustomization" or path != str(file.parent):
            continue
        namespace = doc["metadata"].get("namespace", DEFAULT_NAMESPACE)
        return RootKustomization(
            management_cluster=mc,
            file=file,
            name=doc["metadata"]["name"],
            namespace=namespace,
            git_repository=_ref(
                spec.get("sourceRef") or {}, namespace, "GitRepository"
            ),
            decryption_secret=_ref(
                (spec.get("decryption") or {}).get("secretRef") or {}, namespace
            ),
        )
    raise NoRootError(file)


class KindTestConfig:
    """kind-test.yaml's `settings` for the repository in `repo_dir`."""

    def __init__(self, repo_dir: Path, settings: dict) -> None:
        self.repo_dir = repo_dir
        self.settings = settings
        self.examples: dict[str, dict] = settings.get("examples") or {}
        for name, binding in self.examples.items():
            if not (binding or {}).get("paths"):
                raise NoExamplePathsError(name)

    def management_clusters(self) -> list[str]:
        return management_clusters(
            self.repo_dir, self.settings.get("managementClusters")
        )

    def roots(self) -> list[RootKustomization]:
        return [
            root_kustomization(self.repo_dir, mc) for mc in self.management_clusters()
        ]

    def root(self, mc: str) -> RootKustomization:
        """The root Kustomization of the management cluster `mc`."""
        return root_kustomization(self.repo_dir, mc)

    def git_repositories(self) -> list[Ref]:
        """The GitRepositories the roots read, which the test points at the branch."""
        return sorted({r.git_repository for r in self.roots() if r.git_repository})

    def decryption_secrets(self) -> list[Ref]:
        """The Secrets the roots decrypt with, which the test fills with the master key."""
        return sorted(
            {r.decryption_secret for r in self.roots() if r.decryption_secret}
        )

    def example_skip_reason(self, name: str) -> str | None:
        """Why the checks of the example `name` don't run, or None when they do."""
        binding = self.examples.get(name)
        if binding is None:
            return f"kind-test.yaml has no binding for the example '{name}'"
        applied = set(self.management_clusters())
        for path in binding["paths"]:
            parts = Path(path).parts
            if not (self.repo_dir / path).exists():
                return (
                    f"The example '{name}' isn't in this repository: {path} isn't in the "
                    "repository. Its binding is in tests/ats/kind-test.yaml."
                )
            if (
                len(parts) > 1
                and parts[0] == MANAGEMENT_CLUSTERS_DIR
                and parts[1] not in applied
            ):
                return (
                    f"The example '{name}' is in the management cluster '{parts[1]}', which the "
                    "test doesn't apply: see managementClusters in tests/ats/kind-test.yaml."
                )
        return None

    def skipped_assertion_dirs(self) -> dict[str, str]:
        """The assertion directories of the examples that are skipped, with the reason."""
        skipped: dict[str, str] = {}
        for name, binding in self.examples.items():
            reason = self.example_skip_reason(name)
            if reason:
                skipped |= {d: reason for d in binding.get("assertions") or []}
        return skipped

    def node_pools(self) -> dict[str, dict[str, set[str]]]:
        """The node pools of each workload cluster, `namespace/name`, by namespace."""
        return {
            namespace: {f"{namespace}/{c}": set(p) for c, p in (clusters or {}).items()}
            for namespace, clusters in (self.settings.get("nodePools") or {}).items()
        }

    def cluster_base_apps(self) -> dict[str, list[str]]:
        """The HelmReleases a gated cluster, `namespace/name`, applies before it's Available."""
        return dict(self.settings.get("clusterBaseApps") or {})

    def secret_store(self) -> tuple[str, list[dict]] | None:
        """The name and data of the stand-in secret store, if there is one."""
        store = self.settings.get("secretStore")
        if not store:
            return None
        return store["name"], list(store.get("data") or [])


@cache
def kind_test_config() -> KindTestConfig:
    """The configuration of this repository, read once."""
    return KindTestConfig(REPO_DIR, load_config())


def examples_required(environ: Mapping[str, str]) -> bool:
    """Whether this is a run of the template's own CI, where every example has to be there."""
    return environ.get("GITHUB_REPOSITORY") == TEMPLATE_REPOSITORY


def require_example(name: str) -> None:
    """Skip the calling test, saying why, unless the example `name` is there. In the template's
    own CI, fail instead."""
    reason = kind_test_config().example_skip_reason(name)
    if not reason:
        return
    if examples_required(os.environ):
        pytest.fail(f"{reason} The template's own CI runs every example check.")
    pytest.skip(reason)
