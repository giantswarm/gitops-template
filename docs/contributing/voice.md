# Voice

How the template's documentation is written: the docs, the READMEs of the example directories and the comments in the
examples. It's for anyone changing them, people and coding agents alike.

It applies to this template only. In your fork, write however suits your team.

A customer reads from the first tutorial to the reference pages, and should hear one voice all the way: someone
plain-spoken who has done this before and is showing you how. GitOps is a dull subject by design. Learning it needn't
be.

## The short version

- Second person. Say "you". Never "we", "our" or "let's". Giant Swarm is "Giant Swarm".
- British English: organisation, behaviour, licence, colour. API kinds and fields keep their own spelling, so the kind is
  `Organization`.
- Plain verbs: build, fix, break, run, change. One idea to a sentence.
- Say what a thing does before why, and say what the reader sees when it goes wrong.
- No hype, no emoji, no exclamation marks.
- Code font for every command, flag, path, file name, kind, field and value.
- Short headings. A directory name or a short phrase, with the full path in the body.

## Two registers

Which one depends on what the page is for.

**Tutorials and explanation pages** (`docs/tutorials`, `docs/explanation`) teach, so they're warm and tell a story:
somewhere between technical documentation and a blog post, leaning slightly towards the dry.

- Open by saying where the reader ends up.
- Carry them from one step to the next with a sentence that says why the next thing comes next.
- A little dry humour is welcome where it helps someone remember or find their way: once or twice a page, never inside a
  step, and never a joke that needs explaining.

> If you'd like your cloud bill back afterwards, the last step deletes the cluster again.

**How-to guides, reference pages, READMEs and comments** (`docs/how-to`, `docs/reference`, the example directories,
`tools`) are for someone who knows what they want, so they're factual and practical.

- Lead with what the page or directory is for, in a sentence or two. Then the steps or the facts.
- No scene-setting and no analogy. A dry aside in parentheses now and then is as far as the humour goes.
- Full sentences all the same, with the reason for a step where the reason helps.

> `fake-flux` emulates what Flux does, locally, so you can check your changes before you commit them. It catches syntax
> errors, failing patches and other incompatibilities with Flux.

## One analogy

The repository is a planting plan and Flux is the gardener. Every few minutes it walks round, plants what's in the plan
and not yet in the ground, and pulls up what you've taken out of the plan. Application teams get allotments.

That's the only analogy in the documentation. Use it sparingly, where it explains something, and only in tutorials and
explanation pages. Don't stretch it to things it doesn't fit, and don't bring in a second one: two pictures of the same
thing are harder to follow than none. Ordinary figures of speech are fine.

## Honest about rough edges

Say what doesn't work yet, what's fragile, and what the reader has to ask Giant Swarm for. State it plainly and once.
Don't soften a warning: an instruction that keeps a secret out of Git, or stops Flux deleting a cluster, is written as
an instruction.

Before:

> It could be worth considering whether the key file should perhaps be encrypted prior to being added.

After:

> kubectl-gs writes the private key into the file in plain text, so don't add the file to Git until `sops` has
> encrypted it.

## Words to leave out

- Hype and filler: leverage, seamless, robust, powerful, unlock, empower, simply, just, easy, obviously.
- Padding: "Note that", "In order to", "Please", "It is important to".
- Hedging stacks: "it could perhaps be argued that", "in some ways".
- "Journey" for anything a customer does.

Before:

> This tool will run through `yamllint`, `kubeconform` and `validate-helm-values` to verify your manifests pass all
> checks and is likely to succeed in the cluster.

After:

> It runs them through `yamllint`, `kubeconform` and `validate-helm-values`, so that what passes all the checks is
> likely to apply on the cluster.

## One name for each thing

| Write | Not |
| --- | --- |
| management cluster, workload cluster | MC, WC (they stay in placeholders such as `MC_NAME`) |
| organisation; `Organization` for the kind | organization in prose |
| your fork | your copy, your repo |
| Flux `Kustomization` on first mention, then `Kustomization` | a bare "kustomization" |
| `kustomization.yaml` for the kustomize file | "the kustomization" |
| `HelmRelease`s, `ResourceSet`s | HelmReleases, Helm Releases |
| External Secrets Operator, then ESO | external secrets |
| SOPS for the tool, `sops` for the command | Sops |
| secret manager, for AWS Secrets Manager and the like; a `SecretStore` is the object that reads from it | vault, secrets backend |
| multicluster | multi-cluster |
| out-of-band | out of band, OOB |
| kubectl-gs for the tool, `kubectl gs` in commands | kgs |
| the kind test | the ATS tests, the e2e tests |

SOPS on its own, External Secrets Operator on its own, and both together are all valid. Never write as though a
customer needs both.

## Layout

- Wrap prose at 120 columns.
- A GitHub callout (`> [!Caution]`, `> [!Note]`) for a real hazard or a real aside, not for emphasis.
- A README in an example directory has the same shape as its neighbours: what the directory is and what it shows,
  "What's here", "When you copy it", "Read more".
- A comment in an example is an instruction to whoever copies the file. Keep it short and say what to change.
