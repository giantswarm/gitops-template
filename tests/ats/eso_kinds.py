"""The External Secrets Operator kinds the tests read, create or delete: the store and the
`ExternalSecret`s of the examples, and what apps/workload-cluster-secrets pushes with.
"""

from pykube.objects import NamespacedAPIObject


class ExternalSecretCR(NamespacedAPIObject):
    version = "external-secrets.io/v1"
    endpoint = "externalsecrets"
    kind = "ExternalSecret"


class SecretStoreCR(NamespacedAPIObject):
    version = "external-secrets.io/v1"
    endpoint = "secretstores"
    kind = "SecretStore"


class PushSecretCR(NamespacedAPIObject):
    version = "external-secrets.io/v1alpha1"
    endpoint = "pushsecrets"
    kind = "PushSecret"


class PasswordCR(NamespacedAPIObject):
    version = "generators.external-secrets.io/v1alpha1"
    endpoint = "passwords"
    kind = "Password"
