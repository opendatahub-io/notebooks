//import {spawnSync} from "node:child_process";
import * as process from "node:process";

var testcontainersSetup: boolean = false;

export function setupTestcontainers() {
    if (testcontainersSetup) {return}
    testcontainersSetup = true;

    // https://github.com/testcontainers/testcontainers-node/blob/main/docs/configuration.md
    // https://node.testcontainers.org/supported-container-runtimes/
    process.env['DEBUG'] = 'testcontainers';

    switch (process.platform) {
        case "linux": {
            if ('PODMAN_SOCK' in process.env) { process.env['DOCKER_HOST'] = process.env['PODMAN_SOCK'] }
            else {
                let XDG_RUNTIME_DIR = process.env['XDG_RUNTIME_DIR'] || `/var/run/user/${process.env['UID']}`
                process.env['DOCKER_HOST'] = `unix://${XDG_RUNTIME_DIR}/podman/podman.sock`;
            }
            process.env['TESTCONTAINERS_RYUK_DISABLED'] = 'false';
            process.env['TESTCONTAINERS_RYUK_PRIVILEGED'] = 'true';
            break
        }
        case "darwin": {
            // let result = spawnSync('podman', ['machine', 'inspect', '--format={{.ConnectionInfo.PodmanSocket.Path}}']);
            // let dockerHost = result.stdout.toString().trimEnd()
            // process.env['DOCKER_HOST'] = `unix://${dockerHost}`;
            process.env['TESTCONTAINERS_RYUK_DISABLED'] = 'false';
            process.env['TESTCONTAINERS_RYUK_PRIVILEGED'] = 'true';
            break
        }
    }
}