# Configuration file for elyra.
# Pre-generated via `jupyter elyra --generate-config`
# Editted out the rest of the content, use the above command to get additional config sections.

c = get_config()  # ruff: ignore[F821]

#------------------------------------------------------------------------------
# PipelineProcessorRegistry(SingletonConfigurable) configuration
#------------------------------------------------------------------------------

c.PipelineProcessorRegistry.runtimes = ['kfp']
