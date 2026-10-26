# Road not taken: a node:22-slim base + `npx playwright install --with-deps chromium`
# would cut the image from ~2.9 GB to ~600 MB. We keep the full Playwright base so browser
# versions stay in sync with @playwright/test, and so GHA (@codeserver via
# build-notebooks-TEMPLATE) and Jenkins (quay.io/opendatahub/workbench-images-tests) share
# one image definition.
#
# PLAYWRIGHT_VERSION is required and must match @playwright/test in package.json5
# (see scripts/get_playwright_version.py). Example:
#   podman build --build-arg PLAYWRIGHT_VERSION="$(python3 scripts/get_playwright_version.py)" ...
ARG PLAYWRIGHT_VERSION
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble AS builder
ARG PLAYWRIGHT_VERSION
ARG NODE_VERSION

RUN if [ -n "${NODE_VERSION}" ]; then \
      curl --fail --silent --show-error --location \
        "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.gz" | \
        tar --extract --gzip --strip-components=1 --directory=/usr/local; \
    else \
      cp /usr/bin/node /usr/local/bin/node; \
    fi

RUN npm install -g pnpm@11.9.0

WORKDIR /home/pwuser/tests/browser

COPY package.json5 pnpm-lock.yaml pnpm-workspace.yaml ./
RUN PNPM_CONFIG_fund=false pnpm install --frozen-lockfile

FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble
ARG PLAYWRIGHT_VERSION
LABEL org.opendatahub.playwright.version="${PLAYWRIGHT_VERSION}"

COPY --from=builder /usr/local/bin/node /usr/local/bin/node

WORKDIR /home/pwuser/tests/browser
USER pwuser

COPY --from=builder --chown=pwuser:pwuser /home/pwuser/tests/browser/node_modules ./node_modules
COPY --chown=pwuser:pwuser . .

# CI=true selects headless browser projects (chromium, firefox, webkit) in playwright.config.ts.
# Without it, the config falls back to a "Google Chrome" project that expects a branded Chrome
# binary at /opt/google/chrome/chrome, which is not present in this image.
ENV CI=true

ENTRYPOINT ["./node_modules/.bin/playwright", "test", "--project=chromium"]
