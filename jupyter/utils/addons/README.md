# Jupyter Addons

This package contains addons for JupyterLab workbenches.

## Features / Bugs solved here

(second level bullet points indicate features/bugs that appeared due to the first level bullet point solution)

* [RHOAIENG-11156](https://issues.redhat.com/browse/RHOAIENG-11156) - Better feedback for JupyterLab-based workbenches initial load (improve time to first contentful paint)
  * [RHOAIENG-20553](https://issues.redhat.com/browse/RHOAIENG-20553) - CSS is broken when loading the TensorBoard extension

## Usage

The project uses PurgeCSS to tree-shake the PatternFly CSS file, removing unused styles.
The bundled output is generated in the `dist/` directory.

Code generation (generated code in `dist/` is committed to the repository)

```bash
pnpm install
pnpm build
```

Image build (in a Dockerfile)

```Dockerfile
ARG JUPYTER_REUSABLE_UTILS=jupyter/utils
WORKDIR /opt/app-root/bin
COPY ${JUPYTER_REUSABLE_UTILS} utils/
RUN # Apply JupyterLab addons \
    /opt/app-root/bin/utils/addons/apply.sh
```

## Development

### Previewing the demo

No dev server. Build, then open the static demo page:

```bash
pnpm install   # first time only
pnpm build
open dist/index.html       # macOS
xdg-open dist/index.html   # Linux
```

Click **Finish loading** to simulate JupyterLab loading (spinner disappears).

After editing `partial-head.html`, `partial-body.html`, or the PurgeCSS safelist in
`webpack.config.ts`, re-run `pnpm build` and reload the browser tab.

### Build Process

The project uses webpack to tree-shake the PatternFly CSS:

- `pnpm build` — production CSS tree-shake + regenerate demo HTML
- `pnpm build:dev` — development build with source maps + demo HTML
- `pnpm build:clean` — clean output, then build
- `pnpm clean` — remove `dist/` and `.cache/`
- `pnpm watch` — watch CSS rebuild; re-run `./build-demo.sh` after partial HTML edits
- `pnpm test` — build + tree-shake verification (`test-build.sh`)

CI (`.github/workflows/test-addons.yaml`) runs `pnpm test` when files under `jupyter/utils/addons/` change.

## Files

- `apply.sh`: Script to apply the addons to a JupyterLab during Dockerfile build
- `demo/lab-index.template.html`: Minimal `index.html` stub for local preview (not shipped in images)
- `partial-head.html`, `partial-body.html`: HTML content injected into JupyterLab `index.html`
- `build-demo.sh`: Copies the demo template to `dist/` and runs `apply.sh` (mirrors image build)
- `cleanup-webpack-plugin.ts`: Custom webpack plugin for asset cleanup (removes unnecessary files)
- `webpack.config.ts`: Webpack configuration with enhanced tree-shaking
- `dist/pf.css`: Tree-shaken PatternFly CSS file with only the necessary styles (shipped in images)
- `dist/index.html`: Local demo only (not shipped to JupyterLab images)
- `test-build.sh`: Script to verify the tree-shaking effectiveness
