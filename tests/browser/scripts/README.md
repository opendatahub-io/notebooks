_Small utilities in TypeScript._

See top level `/scripts` directory for Bash and Python scripts.
Also see `/ci` directory for yet more scripts.

## start_browser.ts

Starts a Chrome browser that listens on port 9222 for CDP (Chrome DevTools Protocol) connections.
This can be then used to automate the browser from Playwright (in the other scripts here).

## add_snyk_target.ts

_[https://redhat-internal.slack.com/archives/C06FYLF5DQ9/p1731003424810809]_

Adds a Snyk security scan target to [https://app.snyk.io/org/red-hat-openshift-data-science-rhods].
Useful for adding Pipfiles in new release branches for dependency scanning through the Snyk UI.
The UI allows adding only one Pipfile at a time, so this script can be used to add multiple in a loop.

Requires the browser server in `start_browser.ts` to be running.
