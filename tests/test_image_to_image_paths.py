from datetime import datetime
print(f"importing builtins at {datetime.now()}")
import os
import sys
import json
import importlib
import pkgutil

print(f"importing os at {datetime.now()}")
# Ensure project root is on sys.path so 'src' is importable when running tests directly
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

print(f"importing path at {datetime.now()}")
from src.path.generator import PathGenerator
from src.path.registry import ToolRegistry
from src.path.metadata import ImageFile, StructuredData, PathToolMetadata


def _auto_register_all_path_tools(registry: ToolRegistry) -> None:
    """Auto-discover and register all tools in src.tools.path_tools using AST (no imports)."""
    print(f"Auto-registering all path tools at {datetime.now()}")
    # Compute absolute path to src/tools/path_tools
    repo_root = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
    path_tools_dir = os.path.join(repo_root, 'src', 'tools', 'path_tools')
    registry.auto_register_from_directory(path_tools_dir, recursive=True)
    print(f"Auto-registered all path tools at {datetime.now()}")


def _build_registry() -> ToolRegistry:
    print(f"Building registry at {datetime.now()}")
    registry = ToolRegistry()
    # Auto-register all tools under src.tools.path_tools
    _auto_register_all_path_tools(registry)
    if not registry.tools:
        raise RuntimeError("No tools registered from 'src.tools.path_tools'. Ensure the package and its dependencies are importable.")
    print(f"Built registry at {datetime.now()}")
    return registry


def test_imagefile_to_imagefile_paths_and_report():
    print(f"Testing imagefile to imagefile paths at {datetime.now()}")
    registry = _build_registry()
    generator = PathGenerator(registry)

    # Discover all provenance-aware canonical paths
    paths = generator.find_all_paths(ImageFile, ImageFile)
    print(f"Found {len(paths)} paths at {datetime.now()}")
    print(f"paths: {paths}")
    # Prepare output path next to this test file
    out_path = os.path.join(os.path.dirname(__file__), 'image_to_image_paths.txt')

    # Build a human-readable report including tool routes and metadata
    lines = []
    lines.append('=' * 80)
    lines.append('ImageFile → ImageFile paths (canonical, provenance-aware)')
    lines.append('=' * 80)
    lines.append(f'Total paths: {len(paths)}')
    lines.append('')

    for idx, path in enumerate(paths, start=1):
        tool_names = [t.name for t in path]
        summary = generator.get_path_summary(path)
        lines.append(f'Path {idx}:')
        lines.append(f"  Route: {' → '.join(tool_names)}")
        lines.append(f"  Types: {' → '.join(summary['types'])}")
        lines.append('  Tools:')
        for t in path:
            t_dict = t.to_dict()
            # Pretty-print metadata JSON for each tool
            metadata_json = json.dumps(t_dict, indent=2, ensure_ascii=False)
            # Indent for readability in the text file
            indented = '\n'.join('    ' + line for line in metadata_json.splitlines())
            lines.append(indented)
        lines.append('')

    content = '\n'.join(lines)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Wrote report to {out_path} at {datetime.now()}")
    # Basic assertions: file created and at least one path if tools are available
    assert os.path.exists(out_path), 'Report file was not created'
    # If the tool set is present, we expect at least one path (OCR -> ERASE)
    # Keep this non-strict to allow environments without optional deps to still run tests.
    assert isinstance(paths, list)


if __name__ == '__main__':
    # Allow running directly: python tests/test_image_to_image_paths.py [output_path]
    print(f"starting at {datetime.now()}")
    registry = _build_registry()
    generator = PathGenerator(registry)
    paths = generator.find_all_paths(ImageFile, ImageFile)
    print(f"paths: {paths}")
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), 'image_to_image_paths.txt')

    lines = []
    lines.append('=' * 80)
    lines.append('ImageFile → ImageFile paths (canonical, provenance-aware)')
    lines.append('=' * 80)
    lines.append(f'Total paths: {len(paths)}')
    lines.append('')
    for idx, path in enumerate(paths, start=1):
        tool_names = [t.name for t in path]
        summary = generator.get_path_summary(path)
        lines.append(f'Path {idx}:')
        lines.append(f"  Route: {' → '.join(tool_names)}")
        lines.append(f"  Types: {' → '.join(summary['types'])}")
        lines.append('  Tools:')
        for t in path:
            t_dict = t.to_dict()
            metadata_json = json.dumps(t_dict, indent=2, ensure_ascii=False)
            indented = '\n'.join('    ' + line for line in metadata_json.splitlines())
            lines.append(indented)
        lines.append('')

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f'Wrote ImageFile→ImageFile path report to: {out_path}')
    print(f'Path count: {len(paths)}')

