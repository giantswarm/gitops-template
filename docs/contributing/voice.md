# Voice

How the template's documentation is written: the docs, the READMEs of the example directories and the comments in the
examples. It's for anyone changing them, people and coding agents alike.

It applies to this template only. In your fork, write however suits your team.

A customer reads from the first tutorial to the reference pages, and should hear one voice all the way: someone
plain-spoken who has done this before and is showing you how. GitOps is a dull subject by design. Learning it needn't
be.

## Why this page exists

People learn best when they enjoy the read, and this template is how many customers first meet GitOps. So the
tutorials tell a story, and the reference stays out of your way.

Many people change the template, and more and more of them do it through a coding agent. Each has a style of their
own. Without something to work from, the voice shifts a little with every pull request, until the tutorials and the
reference read as if they belonged to different products.

This page is that something. It's a guide, not a gate: it's here so your change sounds like the page it lands in, not
to turn contributions away.

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

**Tutorials and explanation pages** (`docs/tutorials`, `docs/explanation`) teach, so they're warm and tell a story.
[Writing a tutorial](#writing-a-tutorial) below says how, sentence by sentence.

**How-to guides, reference pages, READMEs and comments** (`docs/how-to`, `docs/reference`, the example directories,
`tools`) are for someone who knows what they want, so they're factual and practical.

- Lead with what the page or directory is for, in a sentence or two. Then the steps or the facts.
- No scene-setting and no analogy. A dry aside in parentheses now and then is as far as the humour goes.
- Full sentences all the same, with the reason for a step where the reason helps.

> `fake-flux` emulates what Flux does, locally, so you can check your changes before you commit them. It catches syntax
> errors, failing patches and other incompatibilities with Flux.

## Writing a tutorial

A tutorial reads as if someone who has done this before were sitting next to you while you do it. They tell you what
you're about to build, say what to type, tell you what you'll see, and mention the thing that caught them out the
first time. They don't lecture, they don't sell, and they don't congratulate you.

**Open with where the reader ends up**, in things they can count, and be honest about what it costs.

> By the end of this tutorial you'll have one organisation, one workload cluster in it and one app running on that
> cluster, all described in files in your fork of this repository and applied by Flux. [...] If you'd like your cloud
> bill back afterwards, the last step deletes the cluster again.

Not "In this tutorial we will explore", not "Imagine you're a platform engineer", and no scene-setting.

**Start from the reader's problem, then give the answer as a short instruction.**

> Application teams usually want to deliver their own workloads from their own repository, without a pull request to
> the platform repository for every change [...]. So give each team an allotment.

**Join the steps with spoken signposts.** A step begins with a word you'd say aloud: "Now", "Next", "Once it's up",
"Before you delete the cluster", "So". The sentence says why this step comes now.

> Now swap your cluster's hand-written hello-world for the template.

**Land the point in a short sentence.** After a longer sentence that explains, a short one says what it comes to.
"That's the template." "Nothing fails meanwhile." "It creates no cluster."

> That's the template. On its own it does nothing: no Flux `Kustomization` points at `bases`, so it isn't part of the
> planting plan.

**Say what the reader will see, and how long it takes.** After a command, say what `Ready` looks like and what a wait
feels like. If something fails first and then recovers, say so before it happens, so nobody stops to debug a thing
that's working.

> The cluster takes 15 to 20 minutes to come up, which is long enough for a cup of tea.

**Keep the humour dry and let it come from the work.** It comes from consequences (the cloud bill), from waiting (the
cup of tea) and from understatement. It's a clause, not a sentence of its own, and the paragraph still makes sense
with it taken out. No puns, no pop culture, no jokes at the reader's expense, and none inside a numbered step. If
you're unsure whether a line is funny, leave it out: a tutorial with no jokes is fine, and one with a forced joke
isn't.

**Use the words you'd use talking.**

- Contractions, always: you'll, don't, it's, there's, isn't.
- Present tense for what happens ("Flux applies it"), future only for what the reader will have ("you'll have").
- "you" does the work: "you add a file", not "a file is added" or "the user adds a file".
- Small plain words for big things: a cluster "comes up", a file "goes missing", Flux "leaves it alone" and "pulls it
  up", a value "wins".
- One aside in parentheses per paragraph at most, and only for something true and useful.

**Treat the reader as capable.** Never "simply", "just" or "easy"; they make a reader who's stuck feel stupid. Never
"Congratulations" or "Well done". When a step is hard or awkward, say that it is.

**Close flat.** The last section says what the reader has now and where to go next, as a short list of links. It
doesn't summarise the page and doesn't cheer.

An explanation page uses the same language without the steps: it starts from a question the reader has by now ("what
happens between a push and a running cluster"), answers it in order, and gives the reason for each design choice.

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
