import os
import sys
from datetime import datetime

# Ensure Windows console handles UTF-8 output (avoids UnicodeEncodeError for ✓/✗)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from langchain_core.language_models import BaseChatModel
print(f"importing builtins at {datetime.now()}")
# Ensure project root is on sys.path so 'src' is importable when running tests directly
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import os
from pathlib import Path
from src.executor.flow_state import StateGenerator
from src.executor.execution import ExecutionOrchestrator
print(f"importing path at {datetime.now()}")
# Single import with controlled order via __init__.py
from src.tools.path_tools.ocr import image_ocr
from src.tools.path_tools.translate import translate
from src.tools.path_tools.erase import erase
from src.tools.path_tools.inpaint_text import inpaint_text
from src.agents.llm import setup_llm
from src.executor.conversion import convert_path_to_hybrid_graph, convert_path_to_isolated_graph
print(f"importing llm at {datetime.now()}")
llm = setup_llm("ollama", "gpt-oss:20b")

path_object = [
    {
        "name": "image_ocr",
        "description": "OCR function specifically for image files",
        "function": image_ocr,
        "input_params": ["input_path"],
        "output_params": ["return"],
        "param_values": {
            "input_path": os.path.join(PROJECT_ROOT, "test.png")
        },
        "param_types": {
            "input_path": str,
            "return": dict
        }
    },
    {
        "name": "translate",
        "description": "Translate text in list of objects",
        "function": translate,
        "input_params": ["text_data", "model"],
        "output_params": ["return"],
        "param_values": {
            "text_data": "${image_ocr.return}",  # From OCR output
            "model": llm  # This is non-serializable
        },
        "param_types": {
            "text_data": dict,
            "model": "BaseChatModel",  # Mark as non-serializable type
            "return": dict
        }
    },
    {
        "name": "erase",
        "description": "Remove text from image using LaMa inpainting model",
        "function": erase,
        "input_params": ["input_path", "bbox_data", "output_path"],
        "output_params": ["return"],
        "param_values": {
            "input_path": os.path.join(PROJECT_ROOT, "test.png"),
            "bbox_data": "${image_ocr.return}",
            "output_path": os.path.join(PROJECT_ROOT, "test_clean.png")
        },
        "param_types": {
            "bbox_data": dict,
            "input_path": str,
            "output_path": str,
            "return": str
        }
    },
    {
        "name": "inpaint_text",
        "description": "Main function to inpaint translated text",
        "function": inpaint_text,
        "input_params": ["bbox_data", "image_input", "output_path"],
        "output_params": ["return"],
        "param_values": {
            "bbox_data": "${translate.return}",
            "image_input": os.path.join(PROJECT_ROOT, "test_clean.png"),
            "output_path": os.path.join(PROJECT_ROOT, "test_final.png")
        },
        "param_types": {
            "image_input": str,
            "bbox_data": dict,
            "output_path": str,
            "return": str
        }
    }
]


def main():
    """Main execution example."""
    
    # Generate state schema
    state_gen = StateGenerator(path_object)
    state_schema = state_gen.state_schema
    initial_state = state_gen.ready_state
    
    # Option 1: Use hybrid isolation (recommended)
    # This will isolate GPU/PyTorch tools but run others directly
    print("=== Using Hybrid Isolation Mode ===")
    workflow = convert_path_to_hybrid_graph(path_object, state_schema)
    
    # Option 2: Use full isolation (all tools in separate processes)
    # Uncomment to use this mode instead
    # print("=== Using Full Isolation Mode ===")
    # workflow = convert_path_to_isolated_graph(path_object, state_schema)
    
    # Execute the workflow
    orchestrator = ExecutionOrchestrator()
    
    # Add progress callback for monitoring
    def progress_callback(event: str, data: dict):
        print(f"[Progress] {event}: {data}")
    
    orchestrator.add_progress_callback(progress_callback)
    
    # Execute
    result = orchestrator.execute_workflow(
        workflow=workflow,
        path_object=path_object,
        initial_state=initial_state
    )
    
    # Check results
    if result.success:
        print(f"\n✓ Execution successful!")
        print(f"  Steps completed: {result.steps_completed}")
        print(f"  Final output: {result.final_output}")
        print(f"  Execution path: {result.execution_path}")
    else:
        print(f"\n✗ Execution failed!")
        print(f"  Error: {result.error_info}")


def test_isolation_modes():
    """Test different isolation modes."""
    import os
    
    print("\n" + "="*60)
    print("Testing Process Isolation Modes")
    print("="*60)
    
    # Test 1: No isolation
    print("\n1. Testing with NO isolation:")
    os.environ["GENESIS_ISOLATION_MODE"] = "none"
    try:
        main()
    except Exception as e:
        print(f"   Expected conflict error: {e}")
    
    # Test 2: Smart isolation (default)
    print("\n2. Testing with SMART isolation (isolates GPU tools):")
    os.environ["GENESIS_ISOLATION_MODE"] = "smart"
    main()
    
    # Test 3: Full isolation
    print("\n3. Testing with FULL isolation (all tools isolated):")
    os.environ["GENESIS_ISOLATION_MODE"] = "all"
    main()


if __name__ == "__main__":
    # Set project root environment variable
    os.environ["GENESIS_PROJECT_ROOT"] = str(Path(__file__).parent.parent)
    
    # Run main example
    main()
    
    # Optionally test different modes
    # test_isolation_modes()