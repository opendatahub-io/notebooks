#!/usr/bin/env python3
"""
Enhanced Parser base class supporting nested subcommands
"""
import argparse
from rich.console import Console
from rich_argparse import RichHelpFormatter

class Parser:

    def __init__(self, autoloader):
        self.autoloader = autoloader
        self.parser = argparse.ArgumentParser(
            formatter_class=RichHelpFormatter,
            description="My CLI tool"
        )

        self.parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Enable verbose output'
        )

        self.subparsers = self.parser.add_subparsers(
            dest='command',
            help='Available commands'
        )

    def register_commands(self):
        """Register all loaded commands and handlers."""
        # Register commands (sorted by name ascending)
        for name in sorted(self.autoloader.commands.keys()):
            command_class = self.autoloader.commands[name]
            help_text = command_class.__doc__ or f'Run command {name}'
            subparser = self.subparsers.add_parser(
                name,
                formatter_class=RichHelpFormatter,
                help=help_text
            )
            subparser.add_argument('args', nargs='*', help='Arguments for the command')
            subparser.set_defaults(handler=command_class())

        # Register handlers (sorted by name ascending)
        for name in sorted(self.autoloader.handlers.keys()):
            handler_class = self.autoloader.handlers[name]
            help_text = handler_class.__doc__ or f'Run {name}'
            subparser = self.subparsers.add_parser(
                name,
                formatter_class=RichHelpFormatter,
                help=help_text
            )
            subparser.add_argument('args', nargs='*', help='Arguments')
            subparser.set_defaults(handler=handler_class())

    def print_help(self):
        """Print custom help with separator between commands and handlers."""
        console = Console()

        console.print("[bold orange1]Usage:[/bold orange1] nb [-h] {commands} ...\n")
        console.print("[bold]My CLI tool[/bold]\n")

        console.print("[bold orange1]Commands:[/bold orange1]")
        for name in sorted(self.autoloader.commands.keys()):
            command_class = self.autoloader.commands[name]
            help_text = command_class.__doc__ or f'Run command {name}'
            console.print(f"  {name:<20} {help_text}")

        console.print("\n[bold orange1]Handlers:[/bold orange1]")
        for name in sorted(self.autoloader.handlers.keys()):
            handler_class = self.autoloader.handlers[name]
            help_text = handler_class.__doc__ or f'Run {name}'
            console.print(f"  {name:<20} {help_text}")

        console.print("\n[bold orange1]Options:[/bold orange1]")
        console.print("  -h, --help            show this help message and exit")

    def parse_command(self):
        """Parse arguments and execute the appropriate handler."""
        # Parse all arguments
        parsed_args = self.parser.parse_args()
        
        # Extract verbose flag
        verbose = parsed_args.verbose
        
        if not hasattr(parsed_args, 'handler'):
            self.parser.print_help()
            return
        
        # Pass parsed args to handler
        handler = parsed_args.handler
        
        # Call handler with all arguments
        if hasattr(handler, 'execute'):
            handler.execute(parsed_args.args, verbose=verbose)
        else:
            self.parser.print_help()
