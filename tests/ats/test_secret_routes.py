"""The two routes to a Secret, SOPS and External Secrets Operator: where an example shows one Secret
both ways, the two copies agree, and no Secret is delivered by both at once. They need no cluster,
only kubectl."""

from pathlib import Path

import pytest
import yaml
from flux_builds import Applied, applied_objects, substitute
from kind_config import kind_test_config
from root_build import REPO_DIR
from secret_routes import (
    SecretShape,
    delivered_twice,
    eso_secret,
    example_pairs,
    shape_differences,
    sops_secret,
)


def external_secret(**spec: object) -> dict:
    return {
        "apiVersion": "external-secrets.io/v1",
        "kind": "ExternalSecret",
        "metadata": {"name": "app-user-secrets", "namespace": "org-acme"},
        "spec": spec,
    }


# what sops writes in place of each value
ENCRYPTED = "ENC[AES256_GCM,data:...]"


def encrypted_secret(**fields: object) -> dict:
    """A SOPS-encrypted Secret as it is in its file: the values are ENC[...], the keys and the
    metadata are clear text."""
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "app-user-secrets", "namespace": "org-acme"},
        "data": {"values": ENCRYPTED},
        "sops": {"mac": ENCRYPTED},
        **fields,
    }


WATCH = {"reconcile.fluxcd.io/watch": "Enabled"}
APP_SHAPE = SecretShape(
    namespace="org-acme",
    name="app-user-secrets",
    type="Opaque",
    keys=("values",),
    labels=(("reconcile.fluxcd.io/watch", "Enabled"),),
)


def test_eso_secret_from_data() -> None:
    es = external_secret(
        target={
            "name": "app-user-secrets",
            "template": {"metadata": {"labels": WATCH}},
        },
        data=[{"secretKey": "values", "remoteRef": {"key": "gitops/app"}}],
    )
    assert eso_secret(es) == APP_SHAPE


def test_eso_secret_from_a_template() -> None:
    # without mergePolicy: Merge, the template's data replaces what `data` reads
    es = external_secret(
        target={
            "template": {
                "type": "kubernetes.io/basic-auth",
                "data": {"username": "git", "login": "{{ .value }}"},
            }
        },
        data=[{"secretKey": "value", "remoteRef": {"key": "gitops/login"}}],
    )
    assert eso_secret(es) == SecretShape(
        "org-acme",
        "app-user-secrets",
        "kubernetes.io/basic-auth",
        ("login", "username"),
        (),
    )
    es["spec"]["target"]["template"]["mergePolicy"] = "Merge"
    assert eso_secret(es).keys == ("login", "username", "value")


def test_eso_secret_keys_from_data_from_are_unknown() -> None:
    es = external_secret(dataFrom=[{"extract": {"key": "gitops/app"}}])
    assert eso_secret(es).keys is None


def test_sops_secret_reads_the_clear_text_of_the_file() -> None:
    secret = encrypted_secret(stringData={"extra": ENCRYPTED}, type="Opaque")
    secret["metadata"]["labels"] = WATCH
    assert sops_secret(secret) == SecretShape(
        "org-acme",
        "app-user-secrets",
        "Opaque",
        ("extra", "values"),
        (("reconcile.fluxcd.io/watch", "Enabled"),),
    )


def test_shape_differences_none() -> None:
    assert shape_differences(APP_SHAPE, APP_SHAPE) == []


def test_shape_differences() -> None:
    sops = APP_SHAPE._replace(
        type="kubernetes.io/basic-auth", keys=("extra",), labels=()
    )
    assert shape_differences(APP_SHAPE, sops) == [
        "type: ExternalSecret 'Opaque', SOPS 'kubernetes.io/basic-auth'",
        "keys: ExternalSecret ['values'], SOPS ['extra']",
        "labels: ExternalSecret {'reconcile.fluxcd.io/watch': 'Enabled'}, SOPS {}",
    ]
    assert shape_differences(APP_SHAPE._replace(keys=None), APP_SHAPE) == [
        "keys: ExternalSecret reads them with dataFrom, so they can't be compared"
    ]


def test_substitute() -> None:
    assert substitute("${cluster_name}-x-${other}", {"cluster_name": "wc"}) == (
        "wc-x-${other}"
    )


def test_delivered_twice() -> None:
    es = external_secret(target={"name": "app-user-secrets"})
    other = external_secret(target={"name": "other"})
    applied = [
        Applied("", "org-acme", es, "apps/app/externalsecret.yaml"),
        Applied("", "org-acme", other, "apps/other/externalsecret.yaml"),
        Applied("", "org-acme", encrypted_secret(), "apps/app/secret.enc.yaml"),
        # the same name in a workload cluster is another Secret
        Applied(
            "org-acme/wc-kubeconfig",
            "org-acme",
            encrypted_secret(),
            "out-of-band/secret.enc.yaml",
        ),
    ]
    assert delivered_twice(applied) == [
        "Secret 'org-acme/app-user-secrets' on the management cluster is written by the "
        "ExternalSecret in apps/app/externalsecret.yaml and by the SOPS file "
        "apps/app/secret.enc.yaml"
    ]


def test_example_pairs(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    es = external_secret(
        target={"name": "app-user-secrets"},
        data=[{"secretKey": "values", "remoteRef": {"key": "gitops/app"}}],
    )
    (app / "externalsecret.yaml").write_text(yaml.safe_dump(es))
    # an alternative the kustomization.yaml doesn't list still counts
    (app / "secret.enc.yaml").write_text(yaml.safe_dump(encrypted_secret()))
    (app / "unrelated.yaml").write_text(yaml.safe_dump({"kind": "ConfigMap"}))
    pairs = example_pairs([app], tmp_path)
    assert [(e.source, s.source) for e, s in pairs] == [
        ("app/externalsecret.yaml", "app/secret.enc.yaml")
    ]


def example_paths() -> list[Path]:
    """The paths of the examples kind-test.yaml binds and the repository has."""
    config = kind_test_config()
    return [
        REPO_DIR / path
        for name, binding in config.examples.items()
        if not config.example_skip_reason(name)
        for path in binding["paths"]
    ]


def test_examples_show_one_secret_the_same_way_by_both_routes() -> None:
    paths = example_paths()
    if not paths:
        pytest.skip("kind-test.yaml binds no example this repository has.")
    problems = [
        f"{e.source} and {s.source}: {d}"
        for e, s in example_pairs(paths, REPO_DIR)
        for d in shape_differences(e.shape, s.shape)
    ]
    assert not problems, "\n".join(problems)


@pytest.fixture(
    scope="module",
    params=kind_test_config().roots(),
    ids=lambda r: r.management_cluster,
)
def applied(request: pytest.FixtureRequest) -> list[Applied]:
    """What each management cluster's root Kustomization applies, and the Kustomizations
    below it that read this repository."""
    return applied_objects(REPO_DIR, request.param.file)


def test_no_secret_is_delivered_by_both_routes(applied: list[Applied]) -> None:
    # kustomize-controller and External Secrets Operator would overwrite each other's copy
    problems = delivered_twice(applied)
    assert not problems, "\n".join(problems)
