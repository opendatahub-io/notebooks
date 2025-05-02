c = get_config()
# Disable unsupported exporters
c.WebPDFExporter.enabled = False
c.QtPDFExporter.enabled = False
c.QtPNGExporter.enabled = False
