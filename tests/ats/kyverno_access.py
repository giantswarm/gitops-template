"""What a management cluster allows and refuses Kyverno's background controller, with the
rights kyverno_rbac replicates, asked like the `automation` ServiceAccounts' in
automation_access."""

from automation_access import Access
from automation_accounts import DEFAULT_NAMESPACE
from kyverno_rbac import NAMESPACE, SERVICE_ACCOUNT


def kyverno_access(org: str) -> list[Access]:
    """Creating ExternalSecrets in the organisation namespace `org`, and not elsewhere."""
    eso = (NAMESPACE, "create", "external-secrets.io", "externalsecrets")
    return [
        Access(*eso, org, True, SERVICE_ACCOUNT),
        Access(*eso, DEFAULT_NAMESPACE, False, SERVICE_ACCOUNT),
    ]
