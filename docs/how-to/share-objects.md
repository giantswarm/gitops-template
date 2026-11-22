# Give every organisation the same object

Every organisation may need the same object, such as a registry pull secret or a CA bundle. Rather than a copy in
Git for each organisation, keep one in a base and list that base in every organisation's `namespace` directory. It's
plain kustomize, with only namespaced objects, so it needs no rights beyond the `org-*` namespaces.

## Share an object

The example has two parts:

- [bases/shared_objects](/bases/shared_objects/) holds the `shared-ca-bundle` ConfigMap, with no namespace, and the
  `kustomization.yaml` that lists it. Put your own objects here, with no namespace either.
- [management-clusters/MC_NAME/organizations/ORG_NAME/namespace/shared-objects](/management-clusters/MC_NAME/organizations/ORG_NAME/namespace/shared-objects/)
  lists the base, with no namespace either. The organisation's `namespace/kustomization.yaml` lists `shared-objects`,
  and the organisation's namespace Flux `Kustomization`, `namespace.yaml`, puts it in the organisation's namespace with
  its `targetNamespace`, see [The organisation's name](../reference/repo-structure.md#the-organisations-name):

    ```yaml
    apiVersion: kustomize.config.k8s.io/v1beta1
    kind: Kustomization
    resources:
      - ../../../../../../bases/shared_objects
    ```

Each organisation's namespace `Kustomization` applies its `namespace` directory, and with it the `shared-objects` its
`kustomization.yaml` lists, so Flux creates a copy in the namespace of every organisation that lists the base. A change
to the base in Git reaches every copy at the next reconcile, and Flux puts back a copy that someone changed in the
cluster. The kind test checks both, see [Shared objects](../reference/ci-checks.md#shared-objects).

## Share a secret

Don't put a Secret itself in the base: every organisation's copy would carry the same value in Git. SOPS can't help
either, as the file would have to name a namespace to keep its checksum, and the base names none. Put an
`ExternalSecret` in the base instead. Each organisation's copy then reads the value from your secret manager through
the `SecretStore` in its own namespace, see
[Create a `SecretStore` for your secret manager](./external-secrets.md#create-a-secretstore-for-your-secret-manager).
Give the stores the same name in every organisation, so one `secretStoreRef` in the base works for all of them.

For example, a registry pull secret, in `bases/shared_objects/registry-pull-secret.yaml`:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: registry-pull-secret
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: SecretStore
    name: STORE_NAME
  target:
    name: registry-pull-secret
    template:
      type: kubernetes.io/dockerconfigjson
  data:
    - secretKey: .dockerconfigjson
      remoteRef:
        key: REGISTRY_CREDENTIALS_KEY
```

List it in the base's `kustomization.yaml`, next to `shared-ca-bundle.yaml`.

## Add another organisation

To give another organisation the object, copy the `shared-objects` directory into its `namespace` directory and add
`shared-objects` to the `resources` of its `namespace/kustomization.yaml`:

```sh
export ORG_DIR=management-clusters/MC_NAME/organizations/OTHER_ORG
cp -r management-clusters/MC_NAME/organizations/ORG_NAME/namespace/shared-objects ${ORG_DIR}/namespace/
yq -i '.resources += ["shared-objects"]' ${ORG_DIR}/namespace/kustomization.yaml
```

The relative path to the base is the same from every organisation's `namespace`, so the copy needs no change. To take
the object away from an organisation, remove `shared-objects` from its list and delete the directory: Flux deletes its
copy at the next reconcile.
