import { test, expect } from '@playwright/test';
import * as k8s from '@kubernetes/client-node';

async function getConsoleUrl(): Promise<string> {
  const kc = new k8s.KubeConfig();
  try {
    kc.loadFromDefault(); // reads KUBECONFIG env var set by shift-left
  } catch (e) {
    throw new Error(`Failed to load kubeconfig: ${e instanceof Error ? e.message : String(e)}`, { cause: e });
  }
  const customApi = kc.makeApiClient(k8s.CustomObjectsApi);
  let route: object;
  try {
    route = await customApi.getNamespacedCustomObject({
      group: 'route.openshift.io', version: 'v1', namespace: 'openshift-console', plural: 'routes', name: 'console'
    }) as object;
  } catch (e) {
    throw new Error(`Failed to fetch openshift-console route: ${e instanceof Error ? e.message : String(e)}`, { cause: e });
  }
  const host = (route as { spec?: { host?: string } }).spec?.host;
  if (!host) {
    throw new Error('openshift-console route has no spec.host');
  }
  return `https://${host}`;
}

// Resolved in beforeAll so a hung K8s API call fails fast with a clear message.
let consoleUrl: string;

test.beforeAll("fetch consoleUrl", async () => {
  test.setTimeout(30_000);
  consoleUrl = await getConsoleUrl();
});

test.use({ ignoreHTTPSErrors: true });

test('@smoke @openshift OCP console loads', async ({ page }) => {
  await page.goto(consoleUrl, { waitUntil: 'load' });
  // Console shows login page or redirects to OAuth — either counts
  await expect(page).toHaveTitle(/Log in|OpenShift|Red Hat/i);
});
