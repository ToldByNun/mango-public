# Verification

Build / Test / Verify Loop — automatisierte Verifikation nach Agent-Aktionen.

**Sprache:** Python

## Geplante Komponenten

- `VerificationLoop` — run, parse_output
- `Verifier` — build, test, lint
- `VerificationResult` — success, errors, artifacts

## Struktur

```
verification/
└── python/
    └── runners/   # Projekt-Profile (npm, cargo, cmake, pytest)
```
