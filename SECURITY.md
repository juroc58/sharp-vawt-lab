# Security Policy

This is a solo research project (a numerical lab for the Sharp cycloturbine), not a production library.

## Reporting a Vulnerability

Use GitHub's private "Report a vulnerability" feature (Security tab → Advisories). Do **not** open a public issue for anything that could be a security concern.

## Scope

**In scope** (please report):

- Path traversal or arbitrary file reads via `polar_dir` or `param_dict`
- Resource exhaustion from unbounded simulation parameters
- Anything that makes `vawt_core` execute attacker-controlled input as code rather than treat it as data

**Out of scope** (do not report):

- Numerical inaccuracy or model-form limitations (documented in README)
- Anything requiring the user to edit source code
- Denial-of-service via intentionally long-running simulations (simulation time is user-controlled)

## Supported Versions

Only the latest `main` branch receives security attention. No backports.