# CLAUDE.md — EITaaS-Linux

Guidance for AI agents (Claude, Codex, subagents) working in this repository.
Humans own every decision; AI assistance must be disclosed in upstream submissions.

## What this repository is

Community Linux tooling for Azure Virtual Desktop (US Government cloud) with CAC
smart-card redirection. Two deliverables:

- `src/eitaas/` — stdlib-only Python ≥ 3.10 CLI (`eitaas doctor|smartcard|inspect-profile|certificates`).
  `api.py` is the presentation-neutral facade; frontends never import platform modules directly.
- `packaging/remmina/` — the product client: an isolated one-shot Remmina 1.4.43 + FreeRDP 3.31.0
  bundle with downstream patches and `eitaas_cac_auth.c` (WebKit CAC / PKCS #11 auth).
  `upstream/remmina/` holds the unbranded upstream-candidate exports of the same changes.

Read `README.md`, `docs/adr/*.md`, and `docs/audits/*.md` before changing behavior.
ADR-0002 fixes the product boundary: one-shot `eitaas-remmina PROFILE.rdpw`; no plugin,
no connection-manager mode, no Flatpak/AppImage.

## Non-negotiable security invariants

- Certificate verification stays on. Never add a cert-bypass switch or suggest one.
- Never capture, log, or persist a CAC PIN, OAuth callback, token, or real `.rdpw` content.
  Test fixtures are synthetic (`tests/fixtures/synthetic.rdpw`) — no tenant/workspace/gateway values.
- Refuse FreeRDP's terminal URL/callback OAuth fallback; only identity-broker or embedded WebView.
- Profiles: regular file, owned by the user, mode `0600`, ≤ 1 MiB, `lstat`/`O_NOFOLLOW`, one immutable buffer.
- Errors cross the API boundary already redacted (`redaction.redact`). No full paths, no raw child output.
- Child processes: fixed argv, no shell, timeouts, bounded output, stdio to `DEVNULL` unless required.
- Untrusted `.rdpw` content reaches FreeRDP's native parser only through the explicit allowlist.
- OAuth: `state` + PKCE S256, exact callback scheme/host/port/path, one terminal result per transaction.
- No polkit/pcsc-lite overrides, no automatic trust-store changes, no `sudo` in diagnostics.

## Engineering standards

**Single source of truth (SSOT).**
- Version pins, patch order, and downstream sources live only in `packaging/remmina/sources.json`;
  RPM spec, Debian, Arch, CI, and lifecycle scripts derive from it (`scripts/check-version-consistency.py`
  guards the Python package version). Never hard-code a version string a manifest already holds.
- Cloud constants (authorities, scopes, hosts) are defined once per language and referenced.
- The downstream patch queue and the upstream series must implement the *same* behavior; a fix
  applied to one must be applied to the other in the same PR.
- Documentation states what code does; do not describe controls that are not implemented.

**Clean code.**
- Small, single-purpose functions; explicit ownership of every pointer/handle in C (who frees, on which thread).
- No duplicated decoders/validators — factor and reuse (e.g. one BOM/UTF-16 RDPW decoder).
- No dead code, no commented-out code, no "fix-up of my own earlier commit" left in a series bound upstream.
- Fail closed: every validation failure produces exactly one terminal result and releases resources.
- Prefer stdlib; no new Python runtime dependencies without an ADR.

**Tests.** `PYTHONPATH=src python -m unittest discover -s tests`. Add behavioral tests, not string-grep
tests, when the property can be exercised (parsing, redaction, selection, patch application, builds).
Every PR keeps the suite green and CI green (`.github/workflows/ci.yml`).

## Remmina / FreeRDP upstream conventions

Code destined for `upstream/remmina/` or the GitLab `contrib/*` branches follows Remmina's style:
- Format with `.uncrustify-remmina.cfg` from the Remmina tree (tabs, 8-column indent,
  `type *name` pointer spacing, function-definition brace on its own line, `if (x) {` on one line).
- GLib/GTK idioms: `g_*` allocators paired with `g_free`, WinPR/FreeRDP allocations with `free`;
  GTK calls on the main thread only; `g_object_ref` anything used across a nested main loop.
- Commit subjects use the component prefix (`RDP: ...`), imperative mood, with a body explaining why.
- No EITaaS branding, private paths, core-dump policy, or product-specific lifecycle in upstream patches.
- Describe FreeRDP 3.31.0 as *tested*, and as *required* only for sovereign-cloud SSO-MIB.
- Regenerate patch files with `git format-patch` from real commits; never hand-edit a diff.
- Verify the series applies onto the pinned base with `git am` and builds `remmina-plugin-rdp`
  with `WITH_RDP_AUTH_AAD=ON` and `OFF`.

## Workflow

1. Work from a GitHub issue with acceptance criteria; file one if none exists.
2. Branch per issue, one PR per issue, PR body references the issue and lists verification commands run.
3. Every PR receives an independent adversarial review before merge; findings are fixed on the same PR.
4. Security gate issues (#49–#64) close only after: equivalent downstream + upstream change,
   behavioral tests, sanitizer run where applicable, developer attestation, and hardware validation
   where the criteria require it. Never tick a checkbox on behalf of the developer.
5. Do not push to the GitLab fork or open upstream merge requests; commit locally and report SHAs.
6. Do not commit `.build/`, `dist/`, real profiles, keys, captures, or agent state
   (`.claude/`, `.codex/`, `.agents/`, `AGENTS.local.md`, `CLAUDE.local.md`) — see `.gitignore`.

## Useful paths

- Pinned Remmina source for downstream work: `Remmina-030946c8…` (see `sources.json`); build recipe in
  `packaging/remmina/eitaas-remmina.spec` / `debian/rules` / `arch/PKGBUILD`.
- Local build trees may exist under `.build/` (ignored); reuse `.build/remmina-poc/prefix` for FreeRDP 3.31.0.
- Support matrix and gates: `docs/supported-platforms.md`. Release: `docs/release-checklist.md`.
