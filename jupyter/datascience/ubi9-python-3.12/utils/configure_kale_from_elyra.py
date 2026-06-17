#!/usr/bin/env python3
"""
Configure Kale KFP server connection by reading Elyra runtime config.

This script maps Elyra runtime configuration to Kale configuration format,
handling authentication type conversion and environment variable references.
"""

import json
import os
import shlex
import sys


def configure_kale_from_elyra(elyra_config_path):
    """
    Read Elyra runtime config and configure Kale KFP server connection.

    Args:
        elyra_config_path: Path to Elyra runtime config JSON file

    Returns:
        True if configuration was saved successfully, False otherwise
    """
    if not elyra_config_path:
        print("No Elyra runtime config found")
        return False

    try:
        with open(elyra_config_path, 'r') as f:
            elyra_config = json.load(f)

        metadata = elyra_config.get('metadata', {})

        # Build Kale configuration from Elyra metadata
        kale_config = {}

        # 1. host: Use api_endpoint (required field)
        kale_config['host'] = metadata.get('api_endpoint', '')

        # 2. namespace: Map user_namespace
        if metadata.get('user_namespace'):
            kale_config['namespace'] = metadata['user_namespace']

        # 3. auth_type and auth_config: Map Elyra auth_type to Kale auth_type
        elyra_auth_type = metadata.get('auth_type', 'KUBERNETES_SERVICE_ACCOUNT_TOKEN')

        if elyra_auth_type == 'NO_AUTHENTICATION':
            kale_config['auth_type'] = None
            kale_config['auth_config'] = {}

        elif elyra_auth_type == 'KUBERNETES_SERVICE_ACCOUNT_TOKEN':
            kale_config['auth_type'] = 'kubernetes_service_account_token'
            kale_config['auth_config'] = {
                'token_path': '/var/run/secrets/kubernetes.io/serviceaccount/token'
            }

        elif elyra_auth_type == 'EXISTING_BEARER_TOKEN':
            kale_config['auth_type'] = 'existing_bearer_token'
            # Export token to environment via shell-sourceable file
            api_password = metadata.get('api_password')
            if api_password:
                kale_config['auth_config'] = {'env_var': 'KF_PIPELINES_TOKEN'}
                # Write shell export file so parent script can source it
                env_export_path = os.environ.get('KALE_ENV_EXPORTS', '/tmp/kale-env-exports.sh')
                with open(env_export_path, 'a') as fh:
                    # Use shlex.quote to safely escape token value
                    fh.write(f"export KF_PIPELINES_TOKEN={shlex.quote(api_password)}\n")
            else:
                kale_config['auth_config'] = {}

        elif elyra_auth_type in ['DEX_STATIC_PASSWORDS', 'DEX_LDAP', 'DEX_LEGACY']:
            # DEX authentication cannot be automatically mapped to Kale
            # Elyra: Stores username/password, exchanges for session cookie at runtime
            # Kale: Expects pre-obtained session cookie in env var or file
            # No lossless mapping exists without implementing DEX login flow
            print(f"Warning: Elyra auth type '{elyra_auth_type}' is not compatible with Kale.")
            print("Kale requires a pre-obtained DEX session cookie, but Elyra provides "
                  "username/password credentials.")
            print("Skipping Kale KFP configuration for DEX authentication.")
            return False

        # 4. ssl_ca_cert: Check if KF_PIPELINES_SSL_SA_CERTS env var is set
        ssl_cert_path = os.environ.get('KF_PIPELINES_SSL_SA_CERTS',
                                         '/var/run/secrets/kubernetes.io/serviceaccount/ca.crt')
        if os.path.exists(ssl_cert_path):
            kale_config['ssl_ca_cert'] = ssl_cert_path

        # Only save config if we have a valid host
        if kale_config.get('host'):
            from kale.config import kfp_server_config
            kfp_server_config.save_config(kale_config)
            print(f"Kale KFP server configuration saved successfully: {kale_config}")
            return True
        else:
            print("Warning: No KFP host found in Elyra config, skipping Kale configuration")
            return False

    except Exception as e:
        print(f"Warning: Could not configure Kale KFP server: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    elyra_config_path = os.environ.get('ELYRA_RUNTIME_CONFIG')
    success = configure_kale_from_elyra(elyra_config_path)
    sys.exit(0 if success else 1)
