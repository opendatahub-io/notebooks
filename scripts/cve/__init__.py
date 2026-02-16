"""Shared utilities for CVE scripts."""

import os
import ssl


def create_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that works on macOS with system certificates.

    Tries certifi first, then falls back to extracting certificates from the
    macOS system keychain.  The context is only needed when ``requests`` is not
    installed and we fall back to ``urllib``.
    """
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        import subprocess
        import tempfile
        try:
            result = subprocess.run(
                ["security", "find-certificate", "-a", "-p",
                 "/System/Library/Keychains/SystemRootCertificates.keychain"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False) as f:
                    f.write(result.stdout)
                try:
                    ctx.load_verify_locations(f.name)
                finally:
                    os.unlink(f.name)
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            pass  # Fall back to default behavior
    return ctx
