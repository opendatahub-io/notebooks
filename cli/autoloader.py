#!/usr/bin/env python3
"""
Enhanced autoloader that handles nested subcommands
"""
import importlib
from pathlib import Path
from rich.console import Console

class Autoloader:

    def __init__(self):
        self.console = Console()
        self.commands = {}
        self.handlers = {}

    def load_components(self):
        """Load all commands and handlers dynamically."""
        self.load_commands()
        self.load_handlers()

    def load_commands(self):
        """Dynamically load all command classes from commands/ directory."""
        commands_path = Path(__file__).parent / 'commands'

        for file in commands_path.glob('*.py'):
            if file.name == '__init__.py':
                continue

            module_name = file.stem
            module = importlib.import_module(f'.commands.{module_name}', package=__package__)

            # Assume each file has a class named after the module (e.g., a.py -> CommandA)
            class_name = self._get_class_name(module_name, is_command=True)
            if hasattr(module, class_name):
                self.commands[module_name] = getattr(module, class_name)

    def load_handlers(self):
        """Dynamically load all handler classes from handlers/ directory."""
        handlers_path = Path(__file__).parent / 'handlers'

        for file in handlers_path.glob('*.py'):
            if file.name == '__init__.py':
                continue

            module_name = file.stem
            module = importlib.import_module(f'.handlers.{module_name}', package=__package__)

            # Assume each file has a class named after the module (e.g., run.py -> RunHandler)
            class_name = self._get_class_name(module_name)
            if hasattr(module, class_name):
                self.handlers[module_name] = getattr(module, class_name)

    def _get_class_name(self, module_name, is_command=False):
        """Convert module name to class name (run -> RunHandler, quay -> QuayCommand)."""
        words = module_name.split('_')
        class_base = ''.join(word.capitalize() for word in words)
        return f"{class_base}Command" if is_command else f"{class_base}Handler"
