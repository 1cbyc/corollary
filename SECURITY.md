# Security policy

## Supported versions

Corollary is pre-alpha. Security fixes are made on the latest release only.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report vulnerabilities privately through
[GitHub security advisories](https://github.com/gabe-santana/corollary/security/advisories/new). Include a
description of the issue, the affected version, and steps or a script to reproduce it.

You can expect an acknowledgement within a few days. Once the issue is confirmed, we will work on a fix,
agree on a disclosure timeline with you, and credit you in the release notes unless you prefer otherwise.

## Scope

The areas of Corollary most relevant to security are the places where untrusted model output meets code:

- **Formula evaluation** (`corollary.formula`): formulas proposed by a model are evaluated by a restricted
  AST interpreter that allows only arithmetic and a fixed set of functions. A way to execute arbitrary code,
  read attributes, or exhaust resources through a formula is a vulnerability.
- **Contract parsing** (`corollary.contract`): a model response that causes a crash, or that gets an action
  accepted without validation, is a vulnerability.
- **Tool execution** (`corollary.agent`): the runtime only calls tools registered on the agent, with
  arguments validated against the tool's signature. A way to call anything else is a vulnerability.

Corollary does not sandbox the tools you register. A tool runs with the permissions of your process, so
validate inputs inside tools that touch the filesystem, network or shell.

Model adapters send prompts, including belief values and document text, to the model provider you
configure. Do not put secrets into beliefs or documents that an agent can see.
