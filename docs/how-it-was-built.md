# How AgentWall was built

This is a plain-language account of how AgentWall came together. I kept it
simple on purpose. If you want the gory details, the git log has them. This
document is the story behind that log, written so you can follow what happened
and why.

## The idea

AgentWall is a policy firewall for AI agents. The short version: an AI agent
wants to do something, and AgentWall decides whether it is allowed to.

A request looks like this: some subject (the agent) is trying to do an action
on some resource, with some extra context. For example, `payments_agent_1`
tries to `execute_payment` on `transaction://high-value-001`. AgentWall checks
that against a set of rules written in a YAML file and answers yes or no, and
it keeps a record of every answer it gives.

The first commits show the thing being built bottom up. I started with the
data, then the logic that reads the data, then the parts that remember what
happened.

## The data model comes first

The earliest commits set up the shape of the system.

- `Add data models and rule loading` built the object model. Every rule,
  subject, action, and resource had a place to live, and the code could read a
  policy in from a YAML file.
- `Add first evaluator impl` was the first version of the decision logic. It
  took a request, looked at the rules, and returned a verdict.
- `Add Unresolved conflict case` and `Add test scenarios` added tricky cases
  and the tests to lock them down. The idea of writing a test next to the
  behavior showed up very early and never left.

Around this point I renamed things to keep the file layout sensible
(`Rename source folder`) and settled on the name AgentWall (`Rename project`).

## The engine and its edge cases

The core decision logic grew in `src/engine.py`. It handles a small number of
cases, and each one reflects a real situation:

- Only a permission matches. The action is permitted.
- Only a prohibition matches. The action is blocked.
- Both match. That is a conflict, and it needs rules to sort out who wins.
- Nothing matches. The action gets a default answer, and by default that answer
  is a deny.

The engine also gained a safety net. If something goes wrong internally instead
of crashing, it returns a deny verdict and logs why. A policy firewall that
fails to deny is worse than one that sometimes denies by mistake, so AgentWall
leans that way.

## Conflicts and priorities

`Create conflict resolver` handled the case where a permission and a
prohibition match the same action. A `RulePriority` is a statement that one
rule outranks another. The resolver holds a lookup table of these pairs and
uses it to pick a winner. If no priority covers the pair, the conflict stays
unresolved and the engine falls back to deny.

## Obligations

This is where AgentWall does more than just say yes or no. Sometimes a permit
comes with conditions. An obligation is an action the agent must complete after
it has been allowed to do something. In the flagship example, a high-value
payment is permitted only if the agent files a CTR report afterwards.

The obligation code grew over a few commits:

- `Create obligation manager` tracks obligations and their lifecycle.
- `Add test for obligation manager` pinned the behavior down.
- `Add dispensation handling` added waivers, for the cases where an obligation
  is explicitly forgiven before it runs.
- A later round added fulfillment tracking and deadline checks, so an obligation
  that is not met in time is marked as violated.

Each obligation moves through a lifecycle: pending, fulfilled, violated, or
waived. That lifecycle shows up in the audit log and in the API.

## The audit trail

`Create audit logger` added the memory of the system. Every decision is written
to an entry with the subject, the action, the resource, the verdict, the
explanation, and which rules matched. The next commits wired that logging into
both the engine and the obligation manager, so the log has one continuous
story: a decision happened, and if it created obligations, those events landed
next to it.

## The API

`Integrate api` and `Add api test` exposed all of this over HTTP using FastAPI.
Three routes came from it:

- `POST /evaluate` takes a request and returns the verdict.
- `GET /obligations` lists obligation records, filterable by status.
- `GET /audit-log` returns recent decisions.

This is the surface another program talks to. The polling of deadlines started
in the background when the app started up, and an interactive docs page came
along for free at `/docs`.

## The LangGraph integration

`Init implementation of langgraph integration` and `Add demo script for
langgraph` tied AgentWall into LangGraph, which is a framework for building
stateful AI agents. The pattern here is Extract, Evaluate, Apply:

- Extract turns whatever the agent wants to do into a normal AgentWall request.
- Evaluate runs it through the engine.
- Apply acts on the result, running the tools, and enforces the obligations.

A demo script showed a payments agent that tries operations and gets filtered
through the policy before anything runs. This is the difference between an API
you can call and a guardrail an agent actually has to pass through.

## The round of hardening

In mid-August the work switched from building new parts to locking everything
down. Six batches of changes went in, each fixing a theme:

1. Environment, secrets, and test audit. The tooling got set up properly so
   secrets never get committed and tests run in CI.
2. Core engine correctness. Fulfillment, default behavior, obligation
   registration, and thread safety were tightened up.
3. Persistence. Obligations moved into SQLite with SQLAlchemy, so they survive
   a restart instead of living in memory.
4. A CLI was added, and the LangGraph demo got real enforcement tests.
5. Extended matching, deterministic ordering, and derived obligations. Matching
   supported more operators (greater than, ranges, wildcards, "in" lists), and
   permission rules could provision obligations that get derived and
   deduplicated.
6. API security and tooling hygiene. The API gained an optional key, a
   per-subject rate limit, and configurable CORS.

## Machine-determined authorization

A later pass closed the two gaps that would otherwise let a model assert its own
authorization. The engine gained two new constraint forms that put the decision
in the machine rather than the model:

- **Type reasoning.** "Is this transaction high value?" is now a *type*, decided
  by subclass reasoning over a small ontology (`OntologyClass` /
  `PolicySet.ontology`) via the new `matches_type` constraint. A rule over
  `HighValueTransaction` automatically covers `CrossBorderTransfer` and any
  subclass added later, without editing the rule.
- **Credential-gated approval.** Approval is a pass whose issuer must be listed
  in `PolicySet.credential_authorities` (`credential` constraint). A missing or
  untrusted issuer means no approval, so the model cannot self-assert it.

In the LangGraph integration the extractor stops copying model-written flags
into context. It stages only operator-owned facts into the reserved keys
`_resource_types` and `_credential_issuer` (`resource_classifier` /
`credential_resolver` in `AgentWallConfig`), stripping those keys from model
input first. The flagship policy moved to this pathway
(`policies/p5_composite.yaml`).

The audit log also grew a `policy_version` column — a sha256 of the policy file
at load — so every decision can be reproduced against the exact rules in force.
Existing audit databases are migrated in place (`src/db.py`).

## Where it stands today

The engine, the obligation lifecycle, the audit log, the REST API, and the
LangGraph integration are all implemented and tested. The test suite currently
has 91 tests. The code builds on Pydantic for the model layer, FastAPI for the
API, SQLAlchemy over SQLite for persistence, and LangGraph for the agent wiring.

The short story: start with good data models, add the decision logic, handle the
edge cases, add the obligations and the audit trail, expose it over an API, wire
it into an agent framework, and then spend your time making it safe to run for
real.