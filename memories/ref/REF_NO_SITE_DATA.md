---
name: No Site-Specific Data In Memories
description: Forbids real infrastructure values (hostnames, IPs, IDs, org names, credentials) in any memory — memories describe structure, never site values. Open before writing or reviewing onboarding/update memories.
obligations:
  - Write memories that describe STRUCTURE (paths, config KEY names, generic roles) — NEVER site VALUES (real hostnames, IPs, IDs, org names, credentials).
  - Report a sensitive-value finding to the user IN CHAT ONLY — NEVER as a memory section, to-do, or inventory.
metadata:
  type: reference
  keywords: site data, secrets, pii, infra values, onboarding, redaction, placeholders
---

# No Site-Specific Data In Memories

Memories describe STRUCTURE. NEVER write site VALUES into any memory.

## Forbidden (any memory, any prefix)

- Real hostnames, domains, or URLs of the project's deployments.
- IP addresses (any non-placeholder IPv4/IPv6).
- Ports tied to a real host/service.
- Server, instance, snapshot, account, or project IDs.
- Org, client, or customer names and slugs.
- GitHub org/repo identifiers for a real private or client repo.
- Emails, usernames.
- Credentials, tokens, API keys, private keys.
- Cloud provider account details (account numbers, ARNs, project IDs).
- File:value lists inventorying where secrets live (that list IS the leak).

## Allowed

- File paths.
- Config KEY names — NEVER their values.
- Service roles described generically: "the gateway systemd unit", NEVER a unit name that embeds an org/brand.
- Placeholder values only:

| Kind     | Placeholder         |
| -------- | ------------------- |
| Hostname | `host.example`      |
| IP       | `192.0.2.10`        |
| Email    | `user@example.test` |
| Token    | `<token>`           |
| Repo     | `<org>/<repo>`      |
| Site     | `example-site`      |

## Sensitive-Value Findings

A sensitive value discovered during analysis (real IP, credential, org name, etc.) is REPORTED TO THE USER IN CHAT ONLY. NEVER write it into a memory section, a to-do list, or an inventory — including a "Real-Infra Findings" or similar to-do naming files that hold real values.

## Mechanical Backstop

`swe_pre_memory_index_gate.py` `[site-data]` duty denies memory writes containing non-placeholder IPv4, emails, credentialed URLs, SSH connect strings, private-key blocks, or token prefixes. Regex CANNOT detect real names, domains, service/org identifiers, or topology values with no fixed pattern — the AUTHOR owns catching those. A `[site-data]` denial means a value slipped through; fix the draft. NEVER work around the denial.
