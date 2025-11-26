from jinja2 import Environment
import textwrap

class CleanEnvironment(Environment):
    """Custom Jinja2 environment that automatically dedents indented blocks by 4 spaces."""

    def finalize(self, value):
        """Post-process template output to remove 4-space indentation."""
        if isinstance(value, str):
            lines = value.split('\n')
            result = []

            for line in lines:
                if line and line.startswith('    '):
                    result.append(line[4:])
                else:
                    result.append(line)

            return '\n'.join(result)
        return value
