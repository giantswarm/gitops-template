"""P1, P3, P4: dropping objects from what a Flux Kustomization builds, as deleting their files does.

The app and the application team test_prune removes are listed in kustomization.yaml files, so
leaving their files out of the source would leave the apps Kustomization unable to build.
`$patch: delete` patches in its `spec.patches` drop the objects instead. Flux applies them
before it substitutes the variables, so they name the objects as the Kustomization builds them,
with `${cluster_name}` and `${organization}`. P4 drops a Kustomization from what the management
cluster's Kustomization builds, which substitutes nothing.
"""

import yaml

API_VERSIONS = {
    "HelmRelease": "helm.toolkit.fluxcd.io/v2",
    "OCIRepository": "source.toolkit.fluxcd.io/v1",
    "ConfigMap": "v1",
    "GitRepository": "source.toolkit.fluxcd.io/v1",
    "Kustomization": "kustomize.toolkit.fluxcd.io/v1",
}
# what the apps Kustomization of the out-of-band-no-flux cluster substitutes after it builds
SUBSTITUTED = {"out-of-band-no-flux": "${cluster_name}", "org-name": "${organization}"}


def unsubstituted(value: str, substituted: dict[str, str]) -> str:
    """`value` as a Kustomization builds it, before it replaces the variables of `substituted`
    with their values, its keys."""
    for value_of, variable in substituted.items():
        value = value.replace(value_of, variable)
    return value


def delete_patches(
    keys: list[tuple[str, str, str]], substituted: dict[str, str] = SUBSTITUTED
) -> list[dict]:
    """`spec.patches` entries of a Flux Kustomization that drop the objects `keys` from what
    it builds. `substituted` are the variables it substitutes by their values, the apps
    Kustomization's by default."""
    return [
        {
            "patch": yaml.safe_dump(
                {
                    "$patch": "delete",
                    "apiVersion": API_VERSIONS[kind],
                    "kind": kind,
                    "metadata": {
                        "name": unsubstituted(name, substituted),
                        "namespace": unsubstituted(namespace, substituted),
                    },
                }
            )
        }
        for kind, namespace, name in keys
    ]
