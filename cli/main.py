#!/usr/bin/env python3
"""
CLI main class with dynamic parser and handler loading
"""

from rich.console import Console
from rich_argparse import RichHelpFormatter

from .autoloader import Autoloader
from .config import Config
from .parser import Parser

class CLI:

    def __init__(self):
        """Initialize the CLI with core components."""
        self.console = Console()
        self.autoloader = Autoloader()
        self.config = Config(autoloader=self.autoloader)
        self.parser = Parser(autoloader=self.autoloader)
        self.handlers = {}

    def run(self):
        """Execute the CLI workflow: load config, auto-discover components, then parse commands."""
        self.config.load_configuration()
        self.autoloader.load_components()
        self.parser.register_commands()
        self.parser.parse_command()


def main():
    """
    
    """
    cli = CLI()
    cli.run()


if __name__ == '__main__':
    main()