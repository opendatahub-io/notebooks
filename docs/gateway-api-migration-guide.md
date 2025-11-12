# Migrating Workbench Images to Kubernetes Gateway API

## Overview

When migrating from OpenShift Route + oauth-proxy to Kubernetes Gateway API + kube-rbac-proxy, workbench images require nginx configuration updates to properly handle path-based routing.

## The Core Requirement

**Your workbench image must serve all content from the base path `${NB_PREFIX}`.**

Any call from a browser to a different path, for example `/index.html`, `/api/my-endpoint`, or simply `/`, won't be routed to the workbench container. This is because the routing, handled by the Gateway API, is path-based, using the same value as the environment variable `NB_PREFIX` that is injected into the workbench at runtime.

Example `NB_PREFIX`: `/notebook/<namespace>/<workbench-name>`

## Key Architectural Difference

### OpenShift Route (Old)
```
External: /notebook/user/workbench/app/
           ↓
Route strips prefix
           ↓
Container receives: /app/
```

**Important**: The prefix stripping isn't automatic - it requires implementation:
- **nginx** strips the prefix via rewrite rules
- **Catch-all redirects** like `location / { return 302 /app; }`

Both approaches work because the Route **forwards all traffic** to the pod regardless of path.

### Gateway API (New)
```
External: /notebook/user/workbench/app/
           ↓
Gateway preserves full path (path-based routing)
           ↓
Container receives: /notebook/user/workbench/app/
```

**Critical Difference**: Gateway API uses **path-based routing**. Only requests matching the configured path prefix are forwarded to the pod.

### Why Old Approaches Fail with Gateway API

```
App redirects: /notebook/user/workbench/app → /app
                                               ↓
Browser follows redirect to: /app
                                ↓
Gateway routing rule: /notebook/user/workbench/** (doesn't match /app!)
                                ↓
Pod receives NO traffic → 404 or routing failure
```

**The Problem**: If your application redirects to paths outside `${NB_PREFIX}`, the Gateway cannot route those requests back to your pod. The path-based matching at the Gateway level requires all traffic to stay within the configured prefix.

**Critical Change**: Your application (or reverse proxy) must handle the **full path** including the prefix and never redirect outside of it.

---

## Part 1: For All Workbenches - General Requirements

These requirements apply **regardless of whether you use nginx or application-level path handling**.

### 1. Health Check Endpoints

Your workbench **must** respond to health checks at:

```
GET /{NB_PREFIX}/api
```

This endpoint must return an HTTP 200 status for probes to succeed.

**Example for Python Flask**:
```python
from flask import Flask
import os

app = Flask(__name__)
nb_prefix = os.getenv('NB_PREFIX', '')

@app.route(f'{nb_prefix}/api')
def health_check():
    return {'status': 'healthy'}, 200

@app.route(f'{nb_prefix}/api/kernels')
def kernels():
    # Handle culler endpoint
    return {'kernels': []}, 200

@app.route(f'{nb_prefix}/api/terminals')  
def terminals():
    # Handle culler endpoint
    return {'terminals': []}, 200
```

**Example for Node.js Express**:
```javascript
const express = require('express');
const app = express();
const nbPrefix = process.env.NB_PREFIX || '';

app.get(`${nbPrefix}/api`, (req, res) => {
    res.json({ status: 'healthy' });
});

app.get(`${nbPrefix}/api/kernels`, (req, res) => {
    res.json({ kernels: [] });
});

app.get(`${nbPrefix}/api/terminals`, (req, res) => {
    res.json({ terminals: [] });
});
```

### 2. Culler Endpoints

If your workbench supports culling idle workbenches, you must handle:

```
GET /{NB_PREFIX}/api/kernels
GET /{NB_PREFIX}/api/terminals
```

These should return information about active kernels/terminals, or empty arrays if none exist.

### 3. Use Relative URLs in Your Application

**Critical**: Your application must generate relative URLs, not absolute ones.

```html
<!-- ❌ BAD - Hardcoded absolute path -->
<a href="/menu1">Menu 1</a>
<script src="/static/app.js"></script>
<img src="/images/logo.png" />

<!-- ✅ GOOD - Relative URLs -->
<a href="menu1">Menu 1</a>
<script src="static/app.js"></script>
<img src="images/logo.png" />

<!-- ✅ ALSO GOOD - Framework-generated URLs with base path -->
<a href="{{ url_for('menu1') }}">Menu 1</a>
```

**Why**: Hardcoded absolute paths like `/menu1` will not include the `{NB_PREFIX}`, causing 404 errors. Relative URLs or framework-generated URLs will correctly resolve to `/{NB_PREFIX}/menu1`.

### 4. Configure Your Application's Base Path

If your framework supports it, configure the base path using the `NB_PREFIX` environment variable:

**FastAPI**:
```python
from fastapi import FastAPI
import os

app = FastAPI(root_path=os.getenv('NB_PREFIX', ''))
```

**Flask**:
```python
from flask import Flask
import os

app = Flask(__name__)
app.config['APPLICATION_ROOT'] = os.getenv('NB_PREFIX', '')
```

**Express.js**:
```javascript
const express = require('express');
const app = express();
const nbPrefix = process.env.NB_PREFIX || '';

// Mount all routes under the prefix
const router = express.Router();
// ... define routes on router ...
app.use(nbPrefix, router);
```

**Streamlit**:
```toml
# .streamlit/config.toml
[server]
baseUrlPath = "/notebook/namespace/workbench"  # Set via NB_PREFIX
```

### 5. Limitations: Applications with Hardcoded Absolute Paths

**If your application has hardcoded absolute paths that cannot be changed**, migration becomes very difficult:

```javascript
// ❌ This cannot work with Gateway API unless rewritten
const menuUrl = "/menu1";  // Hardcoded absolute path
fetch(menuUrl).then(...);
```

**Solutions**:
1. **Modify the application** - Change to relative URLs or configurable base path (preferred)
2. **Use nginx with URL rewriting** - nginx can intercept and rewrite some URLs, but this is limited
3. **HTML/JS post-processing** - Intercept responses and rewrite URLs (complex, not recommended)

**Warning**: nginx can rewrite URLs in redirects and some headers, but it **cannot** rewrite URLs embedded in HTML/JavaScript content without complex content manipulation, which is error-prone and slow.

---

## Part 2: For nginx-based Workbenches - Reverse Proxy Configuration

**Use this section if** your application does not support base path configuration and you need nginx to handle the path translation.

### Required nginx Changes

### 1. Remove Problematic Location Blocks

**REMOVE** any overly broad location blocks that cause infinite redirects:

```nginx
# ❌ REMOVE THIS - Too broad, causes infinite loops
location ${NB_PREFIX}/ {
    return 302 $custom_scheme://$http_host/app/;
}
```

**Why**: This matches ALL paths under the prefix, including your application endpoint itself (e.g., `/notebook/user/workbench/app/`), creating redirect loops.

### 2. Update Redirects to Preserve NB_PREFIX

**All redirects must include `${NB_PREFIX}`** to keep requests within the Gateway route:

```nginx
# ❌ BAD - Strips prefix
location = ${NB_PREFIX} {
    return 302 $custom_scheme://$http_host/myapp/;
}

# ✅ GOOD - Preserves prefix
location ${NB_PREFIX} {
    return 302 $custom_scheme://$http_host${NB_PREFIX}/myapp/;
}
```

**Note**: Use `location ${NB_PREFIX}` (without `=`) to handle both with and without trailing slash.

### 3. Add Prefix-Aware Proxy Location

**Add a location block** that matches the full prefixed path and strips the prefix before proxying:

```nginx
location ${NB_PREFIX}/myapp/ {
    # Strip the prefix before proxying to backend
    rewrite ^${NB_PREFIX}/myapp/(.*)$ /$1 break;
    
    # Proxy to your application
    proxy_pass http://localhost:8080/;
    proxy_http_version 1.1;
    
    # Essential for WebSocket support
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    
    # Long timeout for interactive sessions
    proxy_read_timeout 20d;
    
    # Pass through important headers
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $custom_scheme;
}
```

### 4. Update Health Check Endpoints

Health checks must also preserve the prefix:

```nginx
# Health check endpoint
location = ${NB_PREFIX}/api {
    return 302 ${NB_PREFIX}/myapp/healthz/;
    access_log off;
}
```

### 5. Add Wildcard server_name Fallback

Gateway API uses different hostnames than OpenShift Routes. Add fallback logic:

```bash
# In run-nginx.sh or startup script
export BASE_URL=$(extract_base_url_from_notebook_args)

# If BASE_URL is empty or invalid, use wildcard server_name
if [ -z "$BASE_URL" ] || [ "$BASE_URL" = "$(echo $NB_PREFIX | awk -F/ '{ print $4"-"$3 }')" ]; then
    export BASE_URL="_"
fi
```

This sets `server_name _;` which accepts requests from any hostname.

### 6. Update kube-rbac-proxy Configuration

Remove trailing slashes from upstream URLs in pod/statefulset specs:

```yaml
# ❌ BAD
args:
  - '--upstream=http://127.0.0.1:8888/'

# ✅ GOOD
args:
  - '--upstream=http://127.0.0.1:8888'
```

## HTTPRoute Configuration

Ensure your HTTPRoute matches the full prefix path:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: my-workbench
  namespace: <user-namespace>
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: data-science-gateway
      namespace: openshift-ingress
  rules:
    - backendRefs:
        - kind: Service
          name: my-workbench-rbac
          port: 8443
          weight: 1
      matches:
        - path:
            type: PathPrefix
            value: /notebook/<namespace>/<workbench-name>
```

**Important**: The `value` must match the `NB_PREFIX` environment variable set in the pod.

## Reference Implementation

See these files for complete examples:

### Code-Server
- **nginx config**: `codeserver/ubi9-python-3.12/nginx/serverconf/proxy.conf.template_nbprefix`
- **startup script**: `codeserver/ubi9-python-3.12/run-nginx.sh`

### RStudio
- **nginx config**: `rstudio/c9s-python-3.11/nginx/serverconf/proxy.conf.template_nbprefix`
- **startup script**: `rstudio/c9s-python-3.11/run-nginx.sh`

## Understanding nginx Location Matching

nginx location blocks have different matching priorities:

```nginx
# 1. Exact match (highest priority)
location = /exact/path {
    # Only matches /exact/path (no trailing slash)
}

# 2. Prefix match (evaluated in order of length)
location /prefix {
    # Matches /prefix, /prefix/, /prefix/anything
}

# 3. Regex match (not covered here)
```

For Gateway API, you need:

```nginx
# Redirect root to app
location ${NB_PREFIX} {
    return 302 $custom_scheme://$http_host${NB_PREFIX}/myapp/;
}

# Proxy app traffic (longer prefix wins)
location ${NB_PREFIX}/myapp/ {
    proxy_pass http://localhost:8080/;
}
```

Request `/notebook/ns/wb` → matches first location → redirects  
Request `/notebook/ns/wb/myapp/` → matches second location (longer) → proxies
