"""
Genesis source package.

This package contains the main components of the Genesis system including
agents, executors, GUI components, path handling, and various tools.
"""

# Avoid eager subpackage imports to keep import time minimal.
# Subpackages can be imported explicitly by consumers as needed.
__all__ = ["agents", "executor", "gui", "path", "tools"]
