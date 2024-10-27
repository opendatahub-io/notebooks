import { defineConfig, devices } from '@playwright/test';
import * as process from "node:process";

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
// import dotenv from 'dotenv';
// import path from 'path';
// dotenv.config({ path: path.resolve(__dirname, '.env') });

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: './tests',
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Opt out of parallel tests on CI. */
  workers: process.env.CI ? 1 : 1,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: [ ['html', { open: 'never' }], ['line'] ],
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    codeServerSource: {
      image: process.env['TEST_TARGET'],
    },

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',

    // https://github.com/microsoft/playwright/issues/14854#issuecomment-1666185768
    screenshot: "only-on-failure",
  },

  projects: getProjects(),

});

function getProjects() {
  if ('CI' in process.env) {
    /* Configure projects for major browsers */
    return [
      {
        name: 'chromium',
        use: {...devices['Desktop Chrome']},
      },

      {
        name: 'firefox',
        use: {...devices['Desktop Firefox']},
      },

      {
        name: 'webkit',
        use: {...devices['Desktop Safari']},
      }
    ]
  }

  /* Test against branded browsers. */
  return [
    {
      name: 'Google Chrome',
      use: { ...devices['Desktop Chrome'], channel: 'chrome',
        headless: false,  // the CDP browser configured below is not affected by this
        /* custom properties, comment out as needed */
        connectCDP: 9222,  // false | number: connect to an existing browser running at given port
        codeServerSource: {  // prefers url if specified, otherwise will start the specified docker image
          // url: "",  // not-present | string
          image: "quay.io/modh/codeserver:codeserver-ubi9-python-3.9-20241114-aed66a4",  // string
        }
      },
    }
  ]

}
