"""P1: dropping objects from what a Flux Kustomization builds, as deleting their files does.

The App Set test_prune removes is listed in app_sets/kustomization.yaml, so leaving its files out
of the source would leave the apps Kustomization unable to build. `$patch: delete` patches in its
`spec.patches` drop the objects instead. Flux applies them before it substitutes the variables,
so they name the objects as the Kustomization builds them, with `${cluster_name}` and
`${organization}`.
"""

import yaml

API_VERSIONS = {
    "HelmRelease": "helm.toolkit.fluxcd.io/v2",
    "OCIRepository": "source.toolkit.fluxcd.io/v1",
    "ConfigMap": "v1",
}
# what the apps Kustomization of the out-of-band-no-flux cluster substitutes after it builds
SUBSTITUTED = {"out-of-band-no-flux": "${cluster_name}", "org-name": "${organization}"}


def unsubstituted(value: str) -> str:
    """`value` as the apps Kustomization builds it, before it substitutes the variables."""
    for substituted, variable in SUBSTITUTED.items():
        value = value.replace(substituted, variable)
    return value


def delete_patches(keys: list[tuple[str, str, str]]) -> list[dict]:
    """`spec.patches` entries of a Flux Kustomization that drop the objects `keys` from what
    it builds."""
    return [
        {
            "patch": yaml.safe_dump(
                {
                    "$patch": "delete",
                    "apiVersion": API_VERSIONS[kind],
                    "kind": kind,
                    "metadata": {
                        "name": unsubstituted(name),
                        "namespace": unsubstituted(namespace),
                    },
                }
            )
        }
        for kind, namespace, name in keys
    ]
