_Small utilities in TypeScript._

See top level `/scripts` directory for Bash and Python scripts.
Also see `/ci` directory for yet more scripts.

# 📘 Running the Playwright Scripts (`start_browser.ts` & `add_snyk_target.ts`)

This guide explains how to set up your environment and run the two TypeScript scripts located in:

`tests/browser/scripts/`
-   `start_browser.ts` — launches a Chrome instance with remote debugging enabled
-   `add_snyk_target.ts` — connects to that browser and automates Snyk actions

----------

# 1️⃣ Prerequisites

Install **Node.js + npm**:

`brew install node`

(Or download from [https://nodejs.org](https://nodejs.org))

----------

# 2️⃣ Install TypeScript & ts-node

`npm install -g typescript ts-node`

----------

# 3️⃣ Initialize the project (creates package.json)

From the repo root:

`npm init -y`

This generates:

-   `package.json` — declares dependencies and scripts

> **Note:** `npm init -y` creates only `package.json`. The `package-lock.json` file is generated later, by the first `npm install` step below.

----------

# 4️⃣ Install Playwright dependencies

Playwright **must** be installed locally so the scripts can import it:

`npm install playwright`

This updates:

-   `node_modules/` with the dependency
-   `package.json` with `"playwright": "..."`
-   `package-lock.json` with the exact resolved version

Then install browser binaries:

`npx playwright install`

----------

# 5️⃣ Running the scripts

## 🔵 Step 1 — Start the browser

`npx ts-node --esm tests/browser/scripts/start_browser.ts`

This will:

-   Start Chrome with debugging on port **9222**
-   Open a browser window
-   Keep the process running

----------

## 🟣 Step 2 — Run the Snyk automation script

_[https://redhat-internal.slack.com/archives/C06FYLF5DQ9/p1731003424810809]_

Adds a Snyk security scan target to [https://app.snyk.io/org/red-hat-openshift-data-science-rhods].
Useful for adding Pipfiles in new release branches for dependency scanning through the Snyk UI. (pylock.toml files are not supported by Snyk)

The UI allows adding only one Pipfile at a time, so this script can be used to add multiple in a loop.

Requires the browser server in `start_browser.ts` to be running.

In a new terminal:

`npx ts-node --esm tests/browser/scripts/add_snyk_target.ts`

### ⚠️ Log into Snyk

Use the browser window to log in:

[https://app.snyk.io](https://app.snyk.io)

This script will:

-   Connect to the running browser
-   Detect a visible page
-   Navigate to Snyk’s Add Repository workflow
-   Add all configured pipfiles/targets
