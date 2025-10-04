"""
Tools package for Genesis.

This package contains various tool collections including agent tools and path tools.
"""

# Avoid importing subpackages at module import time to reduce startup latency.
# Expose names via __all__; consumers can import subpackages explicitly.
__all__ = ["agent_tools", "path_tools"]
