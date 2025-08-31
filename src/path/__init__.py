"""
Type-Based Routing Orchestration - Path Package
Modular architecture for path generation and tool management
"""

from .metadata import (
    PathToolMetadata, 
    WorkflowType, FileType, AudioFile, ImageFile, VideoFile, TextFile,
    StructuredData, Text, DocumentFile
)
from .decorators import pathtool
from .registry import ToolRegistry
from .generator import (
    PathGenerator, setup_tool_registry, demonstrate_path_generation,
    is_type_compatible, validate_tool_data_flow, get_type_info
)

__all__ = [
    # Core classes
    'PathToolMetadata',
    'ToolRegistry', 
    'PathGenerator',
    
    # Decorators
    'pathtool',
    'tool',
    
    # Type System
    'WorkflowType', 'FileType', 'AudioFile', 'ImageFile', 'VideoFile', 'TextFile',
    'DocumentFile', 'Text', 'StructuredData',
    
    # Type checking functions
    'is_type_compatible', 'validate_tool_data_flow', 'get_type_info',
    
    # Helper functions
    'setup_tool_registry',
    'demonstrate_path_generation'
]

__version__ = "1.0.0"
__author__ = "Type-Based Routing Team"
