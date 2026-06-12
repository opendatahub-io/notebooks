# Road not taken: a node:22-slim base + `npx playwright install --with-deps chromium`
# would cut the image from ~2.9 GB to ~600 MB, but the full Playwright image is already
# cached in CI (used by the @codeserver tests) and keeps browser/dependency versions in sync.
FROM mcr.microsoft.com/playwright:v1.59.1-noble
# NOTE: image tag version must match @playwright/test version in package.json5

RUN npm install -g pnpm@10.33.0

WORKDIR /home/pwuser/tests/browser
USER pwuser

COPY --chown=pwuser:pwuser package.json5 pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY --chown=pwuser:pwuser . .

# CI=true selects headless browser projects (chromium, firefox, webkit) in playwright.config.ts.
# Without it, the config falls back to a "Google Chrome" project that expects a branded Chrome
# binary at /opt/google/chrome/chrome, which is not present in this image.
ENV CI=true

ENTRYPOINT ["pnpm", "exec", "playwright", "test", "--project=chromium"]
