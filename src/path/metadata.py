"""
Tool Metadata - Core data structures for tool type information
Contains ToolMetadata dataclass and structured type hierarchy for type safety
"""

from typing import Any, Dict, List, Callable, Set, Type, Union, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from pathlib import Path


# =============================================================================
# STRUCTURED TYPE HIERARCHY
# =============================================================================

class WorkflowType(ABC):
    """Base class for all workflow types"""
    
    @classmethod
    @abstractmethod
    def is_compatible_with(cls, other_type: Type['WorkflowType']) -> bool:
        """Check if this type can be converted to another type"""
        pass
    
    @classmethod
    @abstractmethod
    def validate_data(cls, data: Any) -> bool:
        """Validate that data matches this type"""
        pass


class FileType(WorkflowType):
    """Base class for all file types"""
    valid_extensions: Set[str] = set()
    
    @classmethod
    def is_compatible_with(cls, other_type: Type[WorkflowType]) -> bool:
        # Files are compatible with same file types or more general FileType
        return (other_type == FileType or 
                issubclass(other_type, FileType) or
                other_type == cls)
    
    @classmethod
    def validate_data(cls, data: Any) -> bool:
        if not isinstance(data, (str, Path)):
            return False
        
        path = Path(data)
        extension = path.suffix.lower()
        
        # If no specific extensions defined, accept any file
        if not cls.valid_extensions:
            return True
            
        return extension in cls.valid_extensions


class Text(WorkflowType):
    """Plain text type represented by a Python str"""
    
    @classmethod
    def is_compatible_with(cls, other_type: Type[WorkflowType]) -> bool:
        # Text only compatible with Text for now
        return other_type in {Text}
    
    @classmethod
    def validate_data(cls, data: Any) -> bool:
        return isinstance(data, str)


class AudioFile(FileType):
    """Audio file types: .mp3, .wav, .flac, etc."""
    valid_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.wma'}
    
    @classmethod
    def is_compatible_with(cls, other_type: Type[WorkflowType]) -> bool:
        return other_type in {AudioFile, FileType}


class ImageFile(FileType):
    """Image file types: .jpg, .png, .gif, etc."""
    valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg'}
    
    @classmethod
    def is_compatible_with(cls, other_type: Type[WorkflowType]) -> bool:
        return other_type in {ImageFile, FileType}


class VideoFile(FileType):
    """Video file types: .mp4, .avi, .mkv, etc."""
    valid_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    
    @classmethod
    def is_compatible_with(cls, other_type: Type[WorkflowType]) -> bool:
        return other_type in {VideoFile, FileType}


class TextFile(FileType):
    """Text file types: .txt, .md, .csv, etc."""
    valid_extensions = {'.txt', '.md', '.csv', '.json', '.xml', '.html', '.py', '.js', '.ts', '.yml', '.yaml'}
    
    @classmethod
    def is_compatible_with(cls, other_type: Type[WorkflowType]) -> bool:
        return other_type in {TextFile, FileType}


class DocumentFile(FileType):
    """Document file types: .pdf (for now)"""
    valid_extensions = {'.pdf'}
    
    @classmethod
    def is_compatible_with(cls, other_type: Type[WorkflowType]) -> bool:
        return other_type in {DocumentFile, FileType}


class StructuredData(WorkflowType):
    """Base class for structured data (JSON/dict types)"""
    
    @classmethod
    def is_compatible_with(cls, other_type: Type[WorkflowType]) -> bool:
        # Any StructuredData can connect to other StructuredData
        # The actual schema validation happens at execution time, not routing time
        return issubclass(other_type, StructuredData)
    
    @classmethod
    def validate_data(cls, data: Any) -> bool:
        # Simple validation - just check if it's a dictionary
        return isinstance(data, dict)

@dataclass
class PathToolMetadata:
    """Metadata for a tool including type signatures and parameter info"""
    name: str
    function: Callable
    description: str
    # Input/output info
    input_key: str  # The parameter name for main input
    output_key: str  # "return" or a key within returned dict
    # Full parameter info
    input_params: List[str]
    output_params: List[str]
    param_types: Dict[str, type]
    # Additional required inputs (multi-input tools)
    required_inputs: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to path dict"""
        return {
            "name": self.name,
            "function": f"<function {self.name}>",
            "description": self.description,
            "input_key": self.input_key,
            "output_key": self.output_key,
            "input_params": self.input_params,
            "output_params": self.output_params,
            "param_types": {k: v.__name__ if hasattr(v, '__name__') else str(v) 
                           for k, v in self.param_types.items()},
            "required_inputs": {k: v.__name__ if hasattr(v, '__name__') else str(v)
                                 for k, v in self.required_inputs.items()}
        }
# param_type = {audio_path: AudioFile, output_path: AudioFile, return: AudioFile}