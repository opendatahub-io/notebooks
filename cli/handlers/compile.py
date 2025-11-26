from pathlib import Path
from jinja2 import FileSystemLoader, TemplateNotFound
import tomllib
import shutil
from rich.console import Console

from cli.jinja2 import CleanEnvironment, UVIncludeExtension

class CompileHandler:
    """Commands to compile composite Dockerfiles and workbench configurations using Jinja2 templating"""

    def __init__(self):
        self.console = Console()
        self.workbench_subdir = 'odh/workbenches'

    def execute(self, args, verbose=False):
        """Execute compile command with arguments."""
        self.verbose = verbose
        
        if not args:
            # No arguments - compile all workbenches
            self.compile_all_workbenches()
            return

        target = args[0]
        output_dir = self._get_option(args, '-o', '--output', 'output')

        # Check if arch is explicitly specified in args
        has_arch_arg = any('arch=' in arg for arg in args)

        # Parse additional parameters for Jinja context
        context = self._parse_context(args)

        # Try to find as workbench first
        workbench_path = self._find_workbench(target)

        if workbench_path:
            self.compile_workbench(workbench_path, output_dir, context, has_arch_arg)
        else:
            self.console.print(f"[red]Error: Workbench '{target}' not found[/red]")
            self._list_available_workbenches()

    def compile_workbench(self, workbench_path, output_dir, context, has_arch_arg=False):
        """Compile a complete workbench (Dockerfile + manifest + other files)."""
        workbench_path = Path(workbench_path).resolve()
        workbench_name = workbench_path.name

        if not workbench_path.exists():
            self.console.print(f"[red]Error: Workbench not found: {workbench_name}[/red]")
            return

        try:
            # Load manifest to get metadata
            manifest_file = workbench_path / 'manifest.toml'
            manifest = self._load_manifest(manifest_file) if manifest_file.exists() else {}

            # Merge manifest data with context (context takes precedence)
            merged_context = {**manifest, **context}

            # Determine architectures to build
            archs = self._get_architectures(merged_context, manifest, has_arch_arg)

            self.console.print(f"[cyan]Compiling workbench: {workbench_name}[/cyan]", highlight=False)
            arch_names = [f"{a['category']}.{a['arch']}" for a in archs]
            self.console.print(f"[cyan]Architectures: {', '.join(arch_names)}[/cyan]", highlight=False)

            # Create output directory structure
            output_path = Path(output_dir) / workbench_name
            output_path.mkdir(parents=True, exist_ok=True)

            # Compile for each architecture
            for arch_info in archs:
                arch_context = {**merged_context, 'arch': arch_info['arch'], 'category': arch_info['category']}
                
                # Compile Dockerfile
                dockerfile = self._find_dockerfile(workbench_path)
                if dockerfile:
                    # Create filename with both category and arch
                    filename_arch = f"{arch_info['category']}.{arch_info['arch']}"
                    self.compile_dockerfile(dockerfile, str(output_path), arch_context, filename_arch)

            # Compile other .j2 files (like pyproject.toml.j2) - only once, not per arch
            for j2_file in workbench_path.glob('*.j2'):
                if j2_file.name != 'Dockerfile.j2':
                    self._compile_j2_file(j2_file, output_path, merged_context)

            # Copy manifest.toml if it exists
            if manifest_file.exists():
                shutil.copy(manifest_file, output_path / 'manifest.toml')
                self.console.print(f"- Copied manifest.toml")

            self.console.print(f"[green]Workbench compiled successfully[/green]")
            self.console.print(f"[green]Output: {output_path}[/green]")

        except Exception as e:
            import traceback
            self.console.print(f"[red]Error: Failed to compile workbench: {e}[/red]")
            self.console.print(f"[red]{traceback.format_exc()}[/red]")

    def compile_all_workbenches(self, output_dir='output'):
        """Compile all available workbenches."""
        components_root = self._find_components_root(Path.cwd())
        if not components_root:
            self.console.print("[red]Error: Could not find components directory[/red]")
            return
        
        workbenches_dir = components_root / self.workbench_subdir
        if not workbenches_dir.exists():
            self.console.print(f"[red]Error: Workbenches directory not found: {workbenches_dir}[/red]")
            return
        
        workbenches = [d for d in workbenches_dir.iterdir() if d.is_dir()]
        
        if not workbenches:
            self.console.print("[yellow]No workbenches found[/yellow]")
            return
        
        self.console.print(f"[cyan]Compiling {len(workbenches)} workbenches...[/cyan]\n")
        
        for workbench_path in sorted(workbenches):
            manifest_file = workbench_path / 'manifest.toml'
            manifest = self._load_manifest(manifest_file) if manifest_file.exists() else {}
            
            # Use empty context, will be populated from manifest
            context = {}
            has_arch_arg = False
            
            self.compile_workbench(workbench_path, output_dir, context, has_arch_arg)
            self.console.print()  # Blank line between workbenches
        
        self.console.print(f"[green]- All workbenches compiled successfully[/green]")

    def compile_dockerfile(self, input_path, output_dir, context, arch=None):
        """Compile a single Dockerfile template."""
        input_path = Path(input_path).resolve()
        output_path = Path(output_dir)

        if not input_path.exists():
            self.console.print(f"[red]Error: File not found: {input_path}[/red]")
            return

        try:
            output_path.mkdir(parents=True, exist_ok=True)

            if arch and 'arch' not in context:
                context['arch'] = arch

            components_root = self._find_components_root(input_path)

            loader_paths = [input_path.parent]
            if components_root:
                loader_paths.append(components_root)
            loader_paths.append(Path.cwd())

            env = CleanEnvironment(
                loader=FileSystemLoader(loader_paths),
                trim_blocks=True,
                lstrip_blocks=True,
                extensions=[UVIncludeExtension]
            )

            # Configure extension with components_root and context
            for ext in env.extensions.values():
                if isinstance(ext, UVIncludeExtension):
                    ext.components_root = components_root
                    ext.context = context

            env.filters['indent'] = lambda s, n=4: '\n'.join(' ' * n + line for line in s.split('\n'))
            env.filters['load_toml'] = lambda path: self._load_toml_file(path, components_root)

            template = env.get_template(input_path.name)
            rendered = template.render(context)

            rendered = self._dedent_output(rendered)

            output_filename = input_path.stem if input_path.suffix == '.j2' else input_path.name

            if arch:
                parts = output_filename.split('.')
                if len(parts) > 1:
                    output_filename = f"{'.'.join(parts[:-1])}.{arch}.{parts[-1]}"
                else:
                    output_filename = f"{output_filename}.{arch}"

            output_file = output_path / output_filename
            output_file.write_text(rendered)

            self.console.print(f"- {output_filename}", highlight=False)

        except TemplateNotFound as e:
            self.console.print(f"[red]Error: Template not found: {e}[/red]")
        except Exception as e:
            self.console.print(f"[red]Error: Failed to compile Dockerfile: {e}[/red]")

    def _compile_j2_file(self, j2_file, output_dir, context):
        """Compile a generic .j2 file."""
        try:
            components_root = self._find_components_root(j2_file)

            loader_paths = [
                j2_file.parent,
                components_root if components_root else Path.cwd(),
                Path.cwd()
            ]

            env = CleanEnvironment(
                loader=FileSystemLoader(loader_paths),
                trim_blocks=True,
                lstrip_blocks=True,
                extensions=[UVIncludeExtension]
            )

            for ext in env.extensions.values():
                if isinstance(ext, UVIncludeExtension):
                    ext.components_root = components_root
                    ext.context = context

            # Add custom filters
            env.filters['indent'] = lambda s, n=4: '\n'.join(' ' * n + line for line in s.split('\n'))
            env.filters['load_toml'] = lambda path: self._load_toml_file(path, components_root)

            template = env.get_template(j2_file.name)
            rendered = template.render(context)

            # Post-process to dedent 4 spaces from all lines
            rendered = self._dedent_output(rendered)

            # Remove .j2 extension
            output_filename = j2_file.stem
            output_file = Path(output_dir) / output_filename
            output_file.write_text(rendered)

            self.console.print(f"- {output_filename}", highlight=False)

        except Exception as e:
            self.console.print(f"[red]Warning: Failed to compile {j2_file.name}: {e}[/red]")

    def _find_workbench(self, workbench_name):
        """Find workbench directory by name in components/odh/workbenches."""
        components_root = self._find_components_root(Path.cwd())
        if not components_root:
            return None

        workbench_path = components_root / self.workbench_subdir / workbench_name

        if workbench_path.is_dir():
            return workbench_path
        return None

    def _list_available_workbenches(self):
        """List available workbenches."""
        components_root = self._find_components_root(Path.cwd())
        if not components_root:
            return

        workbenches_dir = components_root / self.workbench_subdir
        if not workbenches_dir.exists():
            self.console.print(f"[yellow]Warning: Workbenches directory not found: {workbenches_dir}[/yellow]")
            return

        workbenches = [d.name for d in workbenches_dir.iterdir() if d.is_dir()]

        if workbenches:
            self.console.print(f"\n[cyan]Available workbenches:[/cyan]")
            for wb in sorted(workbenches):
                self.console.print(f"  • {wb}")
        else:
            self.console.print(f"[yellow]No workbenches found in {workbenches_dir}[/yellow]")

    def _find_dockerfile(self, directory):
        """Find Dockerfile or Dockerfile.j2 in directory."""
        directory = Path(directory)

        j2_file = directory / 'Dockerfile.j2'
        regular_file = directory / 'Dockerfile'

        if j2_file.is_file():
            return j2_file
        elif regular_file.is_file():
            return regular_file
        return None

    def _load_manifest(self, manifest_file):
        """Load TOML manifest file."""
        try:
            with open(manifest_file, 'rb') as f:
                return tomllib.load(f)
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not load manifest: {e}[/yellow]")
            return {}

    def _load_toml_file(self, path, components_root):
        """Load a TOML file and return its contents."""
        file_path = Path(path)
        if not file_path.is_absolute() and components_root:
            file_path = components_root / path

        try:
            with open(file_path, 'rb') as f:
                return tomllib.load(f)
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not load TOML file {path}: {e}[/yellow]")
            return {}

    def _find_components_root(self, input_path):
        """Find the components root directory by traversing up."""
        current = Path(input_path).resolve()
        if current.is_file():
            current = current.parent

        # Traverse up to find components directory
        while current != current.parent:
            if (current / 'components').is_dir():
                return current / 'components'
            current = current.parent
        return None

    def _get_architectures(self, context, manifest, has_arch_arg=False):
        """Determine which architectures to build."""
        # Check if arch is explicitly set via CLI args
        if has_arch_arg and 'arch' in context:
            return [context['arch']]
        
        # Get from manifest's build.platforms
        try:
            if manifest and 'build' in manifest and 'platforms' in manifest['build']:
                platforms = manifest['build']['platforms']
                
                # Handle nested structure: {cpu: [...], gpu: [...]}
                if isinstance(platforms, dict):
                    result = []
                    for category, archs in sorted(platforms.items()):
                        for arch in archs:
                            if isinstance(arch, dict):
                                # Handle {name: "cuda", version: "12.6"}
                                result.append({
                                    'category': category,
                                    'arch': arch['name'],
                                    'version': arch.get('version', None)
                                })
                            else:
                                # Handle simple string "x86_64"
                                result.append({
                                    'category': category,
                                    'arch': arch,
                                    'version': None
                                })
                    return result
        except (KeyError, TypeError):
            pass
        
        return [{'category': 'default', 'arch': 'x86_64', 'version': None}]

    def _parse_context(self, args):
        """Parse key=value pairs from arguments for Jinja context."""
        context = {}
        for arg in args[1:]:
            if '=' in arg and not arg.startswith('-'):
                key, value = arg.split('=', 1)
                if value.lower() in ('true', 'false'):
                    context[key] = value.lower() == 'true'
                elif value.isdigit():
                    context[key] = int(value)
                else:
                    context[key] = value
        return context

    def _get_option(self, args, *option_names):
        """Extract option value from args."""
        for i, arg in enumerate(args):
            if arg in option_names and i + 1 < len(args):
                return args[i + 1]
        return 'output'

    def _dedent_output(self, text):
        """Remove 4-space indentation from all non-empty lines and strip trailing blank lines except one."""
        lines = text.split('\n')
        result = []

        for line in lines:
            # Only dedent non-empty lines that start with 4 spaces
            if line and line.startswith('    '):
                result.append(line[4:])
            else:
                result.append(line)

        # Remove all trailing blank lines
        while result and result[-1].strip() == '':
            result.pop()

        # Add back ONE blank line at the end
        result.append('')

        return '\n'.join(result)
