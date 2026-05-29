#!/usr/bin/env python3
"""
Configure Kale KFP server connection by reading Elyra runtime config.

This script maps Elyra runtime configuration to Kale configuration format,
handling authentication type conversion and environment variable references.
"""

import json
import os
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

        # 1. host: Use public_api_endpoint if available, otherwise api_endpoint
        kale_config['host'] = metadata.get('public_api_endpoint') or metadata.get('api_endpoint', '')

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
            # Use environment variable reference instead of storing the actual token
            if metadata.get('api_password'):
                # If api_password exists, reference it via env var
                kale_config['auth_config'] = {'env_var': 'KF_PIPELINES_TOKEN'}
            else:
                kale_config['auth_config'] = {}

        elif elyra_auth_type in ['DEX_STATIC_PASSWORDS', 'DEX_LDAP', 'DEX_LEGACY']:
            kale_config['auth_type'] = 'dex'
            # DEX uses username/password from api_username and api_password
            # Kale expects these to be resolved at runtime, not stored in config
            if metadata.get('api_username') and metadata.get('api_password'):
                # Store reference to environment variables instead of actual credentials
                kale_config['auth_config'] = {
                    'env_var_username': 'KF_PIPELINES_USERNAME',
                    'env_var_password': 'KF_PIPELINES_PASSWORD'
                }
            else:
                kale_config['auth_config'] = {}

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
