"""The test's fake SecretStores and their values, which the examples' ExternalSecrets read.

external_secrets.py creates the stores. docs/how-to/external-secrets.md, "A secret store for
testing", has stores of the same name for trying the guides by hand: it lists
`gitops/hello-world-values` with a GitHub token of the reader's own, and names the notification
guide's two keys in its text.
"""

from collections.abc import Iterable

from workload_cluster_secrets import COMMON

FAKE_STORE_DATA = [
    {
        "key": "gitops/hello-world-values",
        "value": "podAnnotations:\n  example.com/source: secret-manager\n",
    },
    # the notification example's tokens; the test never sends them to GitHub
    {"key": "gitops/github-commit-status-token", "value": "not-a-github-token"},
    {"key": "gitops/github-webhook-token", "value": "not-a-webhook-token"},
]

STORE_NAME = "gitops-test"
# the namespaces whose ExternalSecrets read the store: the management cluster's notifications in
#  `default`, and the organisation's notifications and the clusters' in the organisation's,
#  where organization_operator creates it once the namespace exists
DEFAULT_STORE_NAMESPACE = "default"
STORE_NAMESPACES = (DEFAULT_STORE_NAMESPACE, "org-org-name")
STORE_SPEC = {
    "provider": {
        "fake": {
            "data": [
                *FAKE_STORE_DATA,
                {"key": "workload-clusters-common-token", "value": COMMON.value},
            ]
        }
    }
}


def secret_stores(namespaces: Iterable[str] = STORE_NAMESPACES) -> list[dict]:
    """The same store in each of `namespaces`."""
    return [
        {
            "apiVersion": "external-secrets.io/v1",
            "kind": "SecretStore",
            "metadata": {"name": STORE_NAME, "namespace": namespace},
            "spec": STORE_SPEC,
        }
        for namespace in namespaces
    ]
