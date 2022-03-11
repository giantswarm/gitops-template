# Enable automatic updates of an existing App

Follow the below instructions to tell Flux to automatically update an existing App.

Flux will watch for new Docker image tags for your App and use them to update the `.spec.version` field in the App CR. It will do it by pushing commits to this repository.

**Note**, in order to use this mechanism you have to make sure that image tags of your App corresponds to its version, otherwise this process will result in setting meaningless version in the `.spec.version` field.

**Note**, remember to replace `MC_NAME`, `WC_NAME` and `APP_*` placeholders in the instructions with the corresponding MC codename, WC name and App-related data respectively.

## Directory tree

1. Go to the `management-clusters/MC_NAME/management-cluster` directory and create 1 sub-directory there:
* `automatic-updates` - storage for Flux-related resources. Automatic updates require multiple resources, so it is reasonable to configure them in a separate group.
2. Go to the `automatic-updates` directory and create 3 objects there:
* `kustomization.yaml` file - Kustomize binary-related configuration,
* `imageupdate.yaml` file - Flux's [ImageUpdateAutomation CR](https://fluxcd.io/docs/components/image/imageupdateautomations/) with rules to write back to this repository,
* `APP_NAME` directory - storage for App updates configuration.
3. Populate the `imageupdate.yaml` file with the below content:

```
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageUpdateAutomation
metadata:
  name: flux-system
  namespace: flux-system
spec:
  interval: 1m0s
  sourceRef:
    kind: GitRepository
    name: workload-clusters-fleet
  git:
    checkout:
      ref:
        branch: main
    commit:
      author:
        email: fluxcdbot@users.noreply.github.com
        name: fluxcdbot
      messageTemplate: '{{range .Updated.Images}}{{println .}}{{end}}'
    push:
      branch: main
  update:
    path: ./management-clusters/MC_NAME
    strategy: Setters
```

4. Go to the `APP_NAME` directory and create 2 files there:
* `imagerepository.yaml` - Flux's [ImageRepository CR](https://fluxcd.io/docs/components/image/imagerepositories/) pointing to the registry to scan for new tags,
* `imagepolicy.yaml` - Flux's [ImagePolicy CR](https://fluxcd.io/docs/components/image/imagepolicies/) with rules for tags selection.
5. Populate the `imagerepository.yaml` file with the below content:

```
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageRepository
metadata:
  name: APP_NAME
  namespace: flux-system
spec:
  image: APP_REGISTRY_IMAGE
  interval: 1m0s
```

6. Populate the `imagepolicy.yaml` file with the below content:

```
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImagePolicy
metadata:
  name: APP_NAME
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: APP_NAME
  filterTags:
      extract: $version
      pattern: ^v?(?P<version>.*)$
  policy:
    semver:
      range: '>=0.0.1'
```

**Note**, the `filterTags` is processed first and gives opportunity to filter the image tags before they are considered by the policy rule. Here, it is used to skip the heading `v` in version upon passing it to the policy.

Check [Flux docs](https://fluxcd.io/docs/components/image/imagepolicies/#examples) for more examples of possible policies.

5. Go to the parent directory and populate the `kustomization.yaml` file there with the below content:

```
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: flux-system
resources:
- imageupdate.yaml
- APP_NAME/imagepolicy.yaml
- APP_NAME/imagerepository.yaml
```

## MC configuration

1. Go to the `management-clusters/MC_NAME/management-cluster/flux-system` directory
2. Create the `automatic-updates.yaml` file there and populate it with the below content:

```
apiVersion: kustomize.toolkit.fluxcd.io/v1beta1
kind: Kustomization
metadata:
  name: MC_NAME-automatic-updates
  namespace: flux-system
spec:
  serviceAccountName: kustomize-controller
  prune: false
  interval: 1m
  path: "./management-clusters/MC_NAME/management-cluster/automatic-updates"
  sourceRef:
    kind: GitRepository
    name: workload-clusters-fleet
  timeout: 2m
```

3. Edit the `kustomization.yaml` adding the newly created file as a resource:

```
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: flux-system
resources:
- automatic-updates.yaml
```

## App CR version field mark

1. Go to the `management-clusters/MC_NAME/workload-clusters/WC_NAME/apps/APP_NAME` directory
2. Edit the `appcr.yaml` file and mark the `.spec.version` field for update:

```
piVersion: application.giantswarm.io/v1alpha1
kind: App
metadata:
  name: APP_NAME
spec:
  version: 0.1.2 # {"$imagepolicy": "flux-system:APP_NAME:tag"}
```

## (optional) Secrets for scanning private images

1. Create Kubernetes Secret with Docker Registry credentials and save it into `secrets` directory:

```
$ kubectl create secret docker-registry \
flux-pull-secrets \
--namespace flux-system \
--from-file .dockerconfigjson=path/to/.docker/config.json \
--dry-run=client \
-o yaml > management-clusters/MC_NAME/management-cluster/secrets/pullsecrets.enc.yaml
```

2. Import the master GPG public key and encrypt the Kubernetes Secret with it:

```
$ gpg --import management-clusters/MC_NAME/.sops.keys/.sops.master.asc
$ sops --encrypt --in-place management-clusters/MC_NAME/management-cluster/secrets/pullsecrets.enc.yaml
```

3. Go to the `management-clusters/MC_NAME/management-cluster/automatic-updates/APP_NAME` directory
4. Edit the `imagerepository.yaml` file and reference the newly created secrets there:

```
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageRepository
metadata:
  name: APP_NAME
  namespace: flux-system
spec:
  image: APP_REGISTRY_IMAGE
  interval: 1m0s
  secretRef:
    name: flux-pull-secrets
```

5. Go to the `management-clusters/MC_NAME/management-cluster/flux-system` directory
6. Edit the `automatic-updates.yaml` there and add the dependency section. Note some fields have been removed for brevity:

```
apiVersion: kustomize.toolkit.fluxcd.io/v1beta1
kind: Kustomization
metadata:
  name: MC_NAME-automatic-updates
  namespace: flux-system
spec:
  ...
  dependsOn:
  - name: MC_NAME-secrets
```
