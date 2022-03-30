# Enable automatic updates of an existing App

Follow the below instructions to tell Flux to automatically update an existing App.

Flux will watch for new Docker image tags for your App and use them to update the `.spec.version` field in the App CR. It will do it by pushing commits to this repository.

**Note**, in order to use this mechanism you have to make sure that image tags of your App corresponds to its version, otherwise this process will result in setting meaningless version in the `.spec.version` field.

## Export environment variables

**Note**, Management Cluster codename, Organization name, Workload Cluster name and some App-related values are needed in multiple places across this instruction, the least error prone way of providing them is by exporting as environment variables:

```sh
export MC_NAME=CODENAME
export ORG_NAME=ORGANIZATION
export WC_NAME=CLUSTER_NAME
export APP_NAME=APP_NAME
export APP_IMAGE_REGISTRY=APP_IMAGE_REGISTRY
```

## Directory tree

1. Go to the Workload Cluster directory:

```sh
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}
```

2. Create the `automatic-updates` directory there and enter it:

```sh
mkdir automatic-updates
cd automatic-updates
```

3. Create the `imageupdate.yaml` file that defines an automation process for updating Git repository:

```sh
cat <<EOF > imageupdate.yaml
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageUpdateAutomation
metadata:
  name: ${WC_NAME}-updates
  namespace: default
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
    path: ./management-clusters/${MC_NAME}
    strategy: Setters
EOF
```

4. Leave `automatic-updates` directory and go into the App directory:

```sh
cd ../apps/${APP_NAME}
```

5. Create the [ImageRepository CR](https://fluxcd.io/docs/components/image/imagerepositories/) to configure registry to scan for new tags:

```sh
cat <<EOF > imagerepository.yaml
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImageRepository
metadata:
  name: ${APP_NAME}
  namespace: default
spec:
  image: ${APP_IMAGE_REGISTRY}
  interval: 1m0s
EOF
```

6. Create the [ImagePolicy CR](https://fluxcd.io/docs/components/image/imagepolicies/) with rules for tags selection:

```sh
cat <<EOF > imagepolicy.yaml
apiVersion: image.toolkit.fluxcd.io/v1beta1
kind: ImagePolicy
metadata:
  name: ${APP_NAME}
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: ${APP_NAME}
  filterTags:
      extract: \$version
      pattern: ^v?(?P<version>.*)$
  policy:
    semver:
      range: '>=0.0.1'
EOF
```

**Note**, the `filterTags` is processed first and gives opportunity to filter the image tags before they are considered by the policy rule. Here, it is used to skip the heading `v` in version upon passing it to the policy.

Check [Flux docs](https://fluxcd.io/docs/components/image/imagepolicies/#examples) for more examples of possible policies.

7. Go back to the `apps` directory:

```sh
cd ..
```

8. Edit the `kustomization.yaml` file listing newly created files:

```sh
yq -i e ".resources += [\"${APP_NAME}/imagepolicy.yaml\",\"${APP_NAME}/imagerepository.yaml\"] | .resources style=\"\"" kustomization.yaml
```

The resultant file should looks similar to this:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: default
resources:
- ${APP_NAME}/imagepolicy.yaml
- ${APP_NAME}/imagerepository.yaml
```

## App CR version field mark

1. Go to the App directory:

```sh
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
```

2. Mark the `.spec.version` field for update in the App CR:

```sh
# BSD sed
sed -i "" "s/version:.*$/& # {\"\$imagepolicy\": \"default:${APP_NAME}:tag\"}/" appcr.yaml
```

The resultant file should looks similar to this:

```yaml
piVersion: application.giantswarm.io/v1alpha1
kind: App
metadata:
  name: hello-world
spec:
  version: 0.1.2 # {"$imagepolicy": "default:hello-world:tag"}
```

## (optional) Secrets for scanning private images

1. Export path to the Docker config with secrets:

```sh
export DOCKER_CONFIG_JSON=PATH
```

2. Go to the Management Cluster secrets directory:

```sh
cd management-clusters/${MC_NAME}/secrets
```

3. Create Kubernetes Secret with Docker Registry credentials and save it into a file:

```sh
kubectl create secret docker-registry \
flux-pull-secrets \
--namespace default \
--from-file .dockerconfigjson=${DOCKER_CONFIG_JSON} \
--dry-run=client \
-o yaml > pullsecrets.enc.yaml
```

4. Import the master GPG public key and encrypt the Kubernetes Secret with it:

```sh
gpg --import management-clusters/${MC_NAME}/.sops.keys/.sops.master.asc
sops --encrypt --in-place pullsecrets.enc.yaml
```

5. Edit `kustomization.yaml` and list newly created secret as resource:

```sh
yq -i e '.resources += "pullsecrets.enc.yaml" | .resources style=""' kustomization.yaml
```

6. Go to the App directory:

```sh
cd management-clusters/${MC_NAME}/organizations/${ORG_NAME}/workload-clusters/${WC_NAME}/apps/${APP_NAME}
```

7. Edit the `imagerepository.yaml` file and reference the newly created secrets there:

```sh
yq -i eval '.spec.secretRef.name = "flux-pull-secrets"' imagerepository.yaml
```
