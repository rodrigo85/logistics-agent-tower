# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.3.x   | Yes       |
| < 1.3   | No        |

## Reporting a vulnerability

Email **rodrigo.andreatta@gmail.com** with a description, reproduction steps and
impact. You will get an acknowledgement within 72 hours. Please do not disclose
the issue publicly until a fix is available.

## Secrets and configuration

* Never commit `.env`, API keys or database files. `.gitignore` and the
  `detect-private-key` pre-commit hook enforce this.
* `GOOGLE_MAPS_API_KEY`, `GOOGLE_API_KEY` and `OPENAI_API_KEY` are read as
  `SecretStr` and are never logged.
* In production the database URL is injected from GCP Secret Manager (see
  `infra/terraform/gcp/main.tf`).
* The API has no built-in authentication; deploy it behind an identity-aware
  proxy (Cloud Run IAM / IAP, API gateway) and never expose it directly.
