# The image automation example's deploy key

`deploy-key.enc.yaml` holds the private half of the deploy key that the kind test's image automation pushes with, a
`Secret` named `image-updates-deploy-key` with the key in `identity`, encrypted with SOPS for the template's master key.
Its public half is a deploy key with write access on `giantswarm/gitops-template`.

The kind test can't read a GitHub Actions secret of its own: the shared workflow passes it `GITOPS_MASTER_GPG_KEY` and
nothing else. So the test applies this directory with a Flux `Kustomization` that decrypts it with that key, puts
`identity` in the stand-in secret store under `gitops/image-updates-deploy-key`, and deletes the `Kustomization`, which
takes the decrypted `Secret` with it. The example's `ExternalSecret` then reads the key from the store, as it would
from your secret manager, so the `Secret` the automation uses still comes only from External Secrets Operator. See
[Image automation](../../../../docs/reference/ci-checks.md#image-automation) in CI checks.

Anyone with write access to the repository can read the key, as they can the master key (see
[What the key in CI means](../../../../docs/how-to/configure-ci.md#what-the-key-in-ci-means)).

## Replace the key

Never write the private key to a file in the repository, not even for a moment. Generate the key pair outside it,
pipe the private half straight into `sops`, and delete the pair once its public half is a deploy key:

```sh
ssh-keygen -t ed25519 -N "" -C gitops-template-image-updates -f "${TMPDIR:-/tmp}/image-updates"
KEY="${TMPDIR:-/tmp}/image-updates" yq -n '.apiVersion = "v1" | .kind = "Secret"
  | .metadata.name = "image-updates-deploy-key" | .stringData.identity = load_str(strenv(KEY))' \
  | sops --encrypt --filename-override tests/ats/fixtures/image-updates/deploy-key.enc.yaml \
      --input-type yaml --output-type yaml /dev/stdin \
  > tests/ats/fixtures/image-updates/deploy-key.enc.yaml
```

Add `${TMPDIR:-/tmp}/image-updates.pub` as a deploy key with write access on the repository, remove the old one, and
delete both files.
