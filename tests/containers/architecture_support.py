"""Centralized configuration for architecture-specific feature limitations."""

ARCHITECTURE_LIMITATIONS = {
    "s390x": {"pdf_export": False, "pdf_export_reason": "TexLive and Pandoc dependencies not available on s390x"},
    "x86_64": {"pdf_export": True, "pdf_export_reason": "Full support available"},
    "aarch64": {"pdf_export": True, "pdf_export_reason": "Full support available"},
    "ppc64le": {"pdf_export": True, "pdf_export_reason": "Full support available"},
}

# Architecture mapping from uname -m to common names
ARCHITECTURE_NAMES = {"x86_64": "x86_64", "aarch64": "arm64", "ppc64le": "ppc64le", "s390x": "s390x"}
