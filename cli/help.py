"""
Help system with Rich formatting
Provides formatted help output for the CLI
"""

from rich.console import Console
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.table import Table
from rich.align import Align
from typing import Optional


class HelpFormatter:
    """Rich-formatted help system for the CLI"""
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
    
    def show_main_help(self):
        """Display the main CLI help"""
        # Header
        title = Text("ODH Notebooks CLI", style="bold blue")
        version = Text("v1.0.0", style="dim")
        header = Text.assemble(title, " ", version)
        
        # Usage section
        usage_content = Text()
        usage_content.append("nb", style="bold cyan")
        usage_content.append(" [options]\n")
        usage_content.append("nb", style="bold cyan")
        usage_content.append(" [workflow.yaml]")
        
        usage_panel = Panel(
            usage_content,
            title="Usage",
            title_align="left",
            border_style="green"
        )
        
        # Options table
        options_table = Table(show_header=False, box=None, padding=(0, 2))
        options_table.add_column("Option", style="cyan", no_wrap=True)
        options_table.add_column("Description")
        
        options_table.add_row("--debug, -d", "Enable debug mode with detailed logging")
        options_table.add_row("--dry-run", "Show what would be done without executing")
        options_table.add_row("--help, -h", "Show this help message")
        options_table.add_row("--version, -v", "Show version information")
        
        options_panel = Panel(
            options_table,
            title="Options",
            title_align="left",
            border_style="yellow"
        )
        
        # Examples section
        examples_table = Table(show_header=False, box=None, padding=(0, 1))
        examples_table.add_column("Command", style="bold green", no_wrap=True)
        examples_table.add_column("Description", style="dim")
        
        examples_table.add_row("nb", "Start interactive mode")
        examples_table.add_row("nb --debug", "Start with debug logging enabled")
        examples_table.add_row("nb --dry-run", "Preview mode - show actions without executing")
        examples_table.add_row("nb developer.yaml", "Run a specific workflow file")
        
        examples_panel = Panel(
            examples_table,
            title="Examples",
            title_align="left",
            border_style="magenta"
        )
        
        # Features section
        features = Text()
        features.append("• ", style="green")
        features.append("Interactive menu system\n")
        features.append("• ", style="green")
        features.append("Modular architecture with auto-discovery\n")
        features.append("• ", style="green")
        features.append("Workflow automation support\n")
        features.append("• ", style="green")
        features.append("Rich terminal interface\n")
        features.append("• ", style="green")
        features.append("Debug and dry-run modes")
        
        features_panel = Panel(
            features,
            title="Features",
            title_align="left",
            border_style="blue"
        )
        
        # Layout everything
        self.console.print()
        self.console.print(Align.center(header))
        self.console.print()
        self.console.print(usage_panel)
        self.console.print()
        
        # Two column layout for options and examples
        columns = Columns([options_panel, examples_panel], equal=True, expand=True)
        self.console.print(columns)
        self.console.print()
        self.console.print(features_panel)
        self.console.print()
    
    def show_version(self):
        """Display version information"""
        # Create a stylized version display
        version_text = Text()
        version_text.append("ODH Notebooks CLI ", style="bold blue")
        version_text.append("v1.0.0", style="bold green")
        
        # Additional version details
        details = Text()
        details.append("• ", style="dim")
        details.append("Rich terminal interface\n", style="dim")
        details.append("• ", style="dim")
        details.append("Modular plugin system\n", style="dim")
        details.append("• ", style="dim")
        details.append("Workflow automation\n", style="dim")
        details.append("• ", style="dim")
        details.append("Interactive menus", style="dim")
        
        content = Text.assemble(version_text, "\n\n", details)
        
        panel = Panel(
            content,
            title="Version Information",
            title_align="center",
            border_style="blue",
            width=50
        )
        
        self.console.print()
        self.console.print(Align.center(panel))
        self.console.print()
    
    def show_debug_help(self):
        """Show debug mode specific help"""
        debug_panel = Panel(
            Text.assemble(
                "Debug mode is ", Text("enabled", style="bold green"), ".\n\n",
                "Additional features:\n",
                "• Detailed logging output\n",
                "• Component initialization status\n",
                "• Module loading information\n",
                "• Error stack traces\n",
                "• Performance timing\n\n",
                Text("Environment: ", style="bold"), "CLI_DEBUG=1"
            ),
            title="Debug Mode",
            border_style="yellow"
        )
        
        self.console.print(debug_panel)
    
    def show_dry_run_help(self):
        """Show dry-run mode specific help"""
        dry_run_panel = Panel(
            Text.assemble(
                "Dry-run mode is ", Text("enabled", style="bold cyan"), ".\n\n",
                "Behavior:\n",
                "• Commands are analyzed but not executed\n",
                "• Shows what would happen\n",
                "• Safe for testing workflows\n",
                "• No changes are made to the system\n\n",
                Text("Environment: ", style="bold"), "CLI_DRY_RUN=1"
            ),
            title="Dry-Run Mode",
            border_style="cyan"
        )
        
        self.console.print(dry_run_panel)
    
    def show_workflow_help(self):
        """Show workflow-specific help"""
        workflow_content = Text()
        workflow_content.append("Workflow files are YAML files that define automated sequences.\n\n")
        workflow_content.append("Example workflow structure:\n\n", style="bold")
        workflow_content.append("""name: "Developer Setup"
version: "1.0"
steps:
  - name: "Initialize Environment"
    module: "environment"
    action: "setup"
  - name: "Configure Tools"
    module: "tools"
    action: "configure"
""", style="dim")
        
        workflow_panel = Panel(
            workflow_content,
            title="Workflow Files",
            border_style="green"
        )
        
        self.console.print(workflow_panel)


# Convenience functions for easy import
def show_help(console: Optional[Console] = None):
    """Show main help"""
    formatter = HelpFormatter(console)
    formatter.show_main_help()


def show_version(console: Optional[Console] = None):
    """Show version information"""
    formatter = HelpFormatter(console)
    formatter.show_version()


def show_debug_help(console: Optional[Console] = None):
    """Show debug help"""
    formatter = HelpFormatter(console)
    formatter.show_debug_help()


def show_dry_run_help(console: Optional[Console] = None):
    """Show dry-run help"""
    formatter = HelpFormatter(console)
    formatter.show_dry_run_help()


def show_workflow_help(console: Optional[Console] = None):
    """Show workflow help"""
    formatter = HelpFormatter(console)
    formatter.show_workflow_help()