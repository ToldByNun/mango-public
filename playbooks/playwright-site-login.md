---
name: playwright-site-login
triggers: playwright, browser, login, auth, sign-in, credentials, gated page
---

# Playwright: login then open target page

## When
Goal needs a browser page that sits behind a login wall (Playwright / Cursor browser / similar).

## Steps
1. Open the **login URL** first (not the final page).
2. Fill username from env `SITE_USER` (or ask user once if unset).
3. Fill password from env `SITE_PASS` (or ask user once if unset).
4. Submit the login form; wait for post-login URL or a known logged-in selector.
5. Navigate to the **target URL**.
6. Only then scrape / click / assert.

## Do not
- Jump straight to the gated URL and spam retries.
- Hardcode passwords into scripts or chat summaries.
- Re-ask for credentials every turn if env vars or session already exist.

## Per-site overrides
Copy this file to `~/.mango/playbooks/playwright-<site>.md` and set concrete login URL, selectors, and env names for that site.
