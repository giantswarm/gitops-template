"""The values in the test's fake ClusterSecretStore, which the examples' ExternalSecrets read.

external_secrets.py creates the store. docs/appendices.md, "Secret store for testing", has a store
of the same name for trying the guides by hand: it lists `gitops/hello-world-values` with a
GitHub token of the reader's own, and names the notification guide's two keys in its text.
"""

FAKE_STORE_DATA = [
    {
        "key": "gitops/hello-world-values",
        "value": "podAnnotations:\n  example.com/source: secret-manager\n",
    },
    # the notification example's tokens; the test never sends them to GitHub
    {"key": "gitops/github-commit-status-token", "value": "not-a-github-token"},
    {"key": "gitops/github-webhook-token", "value": "not-a-webhook-token"},
]
