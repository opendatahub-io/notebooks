from jinja2.ext import Extension
from jinja2 import nodes, FileSystemLoader, Environment
import tomllib
from pathlib import Path

class UVIncludeExtension(Extension):
    """Custom Jinja2 extension for including dependencies from TOML/TOML.j2 files."""
    tags = {'uv_include'}

    def __init__(self, environment, components_root=None):
        super().__init__(environment)
        self.components_root = components_root
        self.context = {}

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        filename = parser.parse_expression()
        call_node = self.call_method('_uv_include', [filename])
        return nodes.Output([call_node], lineno=lineno)

    def _uv_include(self, path):
        """Load and compile TOML/TOML.j2 files and extract dependencies."""
        file_path = Path(path)
        if not file_path.is_absolute() and self.components_root:
            file_path = self.components_root / path

        try:
            # If it's a .j2 file, compile it first
            if file_path.suffix == '.j2':
                content = self._compile_j2_file(file_path)
            else:
                with open(file_path, 'r') as f:
                    content = f.read()

            # Parse as TOML
            data = tomllib.loads(content)

            # Extract dependencies
            deps = data.get('project', {}).get('dependencies', [])

            if not deps:
                return ""

            # Format as TOML array items (without trailing comma)
            formatted_deps = ',\n'.join(f'    "{dep}"' for dep in deps)
            return formatted_deps + ','  # Add trailing comma for the next item
        except Exception as e:
            return f"# Error loading {path}: {e}"

    def _compile_j2_file(self, file_path):
        """Compile a Jinja2 template file."""
        from .environments import CleanEnvironment

        loader_paths = [file_path.parent, self.components_root or Path.cwd(), Path.cwd()]

        env = CleanEnvironment(
            loader=FileSystemLoader(loader_paths),
            trim_blocks=True,
            lstrip_blocks=True,
            extensions=[UVIncludeExtension]
        )

        # Configure the extension instance with the correct attributes
        for ext in env.extensions.values():
            if isinstance(ext, UVIncludeExtension):
                ext.components_root = self.components_root  # Use self.components_root
                ext.context = self.context  # Use self.context

        template = env.get_template(file_path.name)
        rendered = template.render(self.context)

        # Dedent
        lines = rendered.split('\n')
        result = []
        for line in lines:
            if line and line.startswith('    '):
                result.append(line[4:])
            else:
                result.append(line)

        # Remove trailing blank lines
        while result and result[-1].strip() == '':
            result.pop()

        return '\n'.join(result)
