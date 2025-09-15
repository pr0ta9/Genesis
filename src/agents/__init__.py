"""
Type-Based Routing Orchestration - Agents Package
Modular architecture for agents
"""

from .classifier import Classifier
from .router import Router
from .finalizer import Finalizer
from .precedent import Precedent
from .llm import setup_llm

__all__ = [
    # Core classes
    'Classifier',
    'Router',
    'Finalizer',
    'Precedent',
    'setup_llm',
]

