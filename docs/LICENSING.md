# Licensing & Pricing

---

## Overview

Apex uses a four-tier model: **Free** (forever), **Pro** ($29.99/mo or $249/yr), **Lifetime** ($499, first 500 units), and **Enterprise** (custom). Licenses are validated locally — no phone-home required except for a weekly subscription refresh.

## Tiers

| Tier | Price | Details |
|------|-------|---------|
| **Free** | $0 forever | No license needed. Core features always available. |
| **Trial** | Free for 30 days | Auto-starts on first launch. All Pro features unlocked. |
| **Pro** | $29.99/mo or $249/yr | Full feature set including iOS app. Refreshed via weekly check-in. |
| **Lifetime** | $499 one-time (first 500) | Same as Pro, never expires. Early adopter reward. |
| **Enterprise** | Custom | Multi-tenant, SSO, RBAC, compliance. [Contact us](mailto:hello@use-ash.com). |

## Feature Matrix

| Feature | Free | Trial / Pro / Lifetime | Enterprise |
|---------|------|------------------------|------------|
| Single chat (all backends) | Yes | Yes | Yes |
| Per-chat model routing | Yes | Yes | Yes |
| Memory system (whisper, embeddings) | Yes | Yes | Yes |
| All skills (/recall, /codex, etc.) | Yes | Yes | Yes |
| Alert system | Yes | Yes | Yes |
| Basic dashboard (health, config) | Yes | Yes | Yes |
| **Group chat / channels** | **No** | **Yes** | **Yes** |
| **Multi-agent orchestration** | **No** | **Yes** | **Yes** |
| **Agent profiles (custom personas)** | **No** | **Yes** | **Yes** |
| Multi-tenant isolation | No | No | **Yes** |
| SSO / OIDC | No | No | **Yes** |
| RBAC (admin/viewer roles) | No | No | **Yes** |
| Compliance reporting | No | No | **Yes** |

**Design principle:** The free tier is generous. Multi-model, memory, skills, alerts — all free. Premium gates collaborative and multi-agent features.

## Trial

Every new install starts with a **30-day free trial** of all Pro features. No credit card required. When the trial ends, premium features (groups, orchestration, custom personas) lock — everything else continues working.

## Subscription & Offline Use

- Pro subscriptions refresh automatically in the background (weekly check-in)
- If your machine is offline, a **7-day grace period** keeps your license valid
- When connectivity returns, the refresh resumes automatically
- Cancellation takes effect at the end of your billing period plus the grace period

## Activating a License

Activate from the dashboard or via the API:

```
POST /api/license/activate
{ "key": "your-license-key" }
```

Your license key is emailed after purchase. Paste it into the dashboard settings or use the API endpoint above.

## Uninstall

To remove Apex from your system:

```bash
python3 scripts/uninstall.py
```

This will:

- Stop the running server
- Remove configuration, database, certificates, and license files
- Remove LaunchAgent (if installed)
- **Preserve** your memory files and conversation history by default

To also remove all user data:

```bash
python3 scripts/uninstall.py --purge
```

To fully remove the Apex directory after uninstall:

```bash
rm -rf ~/.apex
```

## Premium Module Encryption

Premium features (groups, orchestration, agent profiles) are encrypted at rest. The server ships `.enc` blobs that are decrypted at startup with a feature key delivered during license activation.

- **Activation:** `POST /api/license/activate` with `{"license": {...}, "feature_key": "base64-fernet-key"}` — stores both the license and the decryption key.
- **Refresh:** Weekly check-in delivers an updated feature key. During key rotation, both `feature_key` (current) and `feature_key_previous` (grace period) are accepted.
- **Deactivation:** Removes the license and the feature key. Premium modules become inert blobs again.
- **Instance binding:** The feature key is stored in an instance-bound keystore (PBKDF2-derived from the installation's unique ID). Copying the keystore to another machine fails.
- **Dev mode:** When running on a non-production port, plaintext `.py` files are loaded directly for IDE and debugging support.

## Notes

- The code is source-available. Licensing gates premium features as a fair exchange for ongoing development — not as DRM.
- Licenses are cryptographically signed and validated locally. No telemetry, no tracking.
- Offline-first: the server works without internet. Only subscription refresh needs periodic connectivity.
