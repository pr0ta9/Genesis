import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure Windows console handles UTF-8 output (avoids UnicodeEncodeError for ✓/✗)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

print(f"importing builtins at {datetime.now()}")

# Ensure project root is on sys.path so 'src' is importable when running tests directly
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

print(f"importing orchestrator at {datetime.now()}")
from src.orchestrator import Orchestrator
from langchain_core.messages import HumanMessage, AIMessage
from src.logging_utils import pretty
import base64
import mimetypes
print(f"importing complete at {datetime.now()}")


def create_image_content_block(image_path: str, text: str = ""):
    """Create multimodal content blocks for testing."""
    content_blocks = []
    
    if text.strip():
        content_blocks.append({
            "type": "text", 
            "text": text
        })
    
    if os.path.exists(image_path):
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        mime_type, _ = mimetypes.guess_type(image_path)
        content_blocks.append({
            "type": "image",
            "base64": image_data,
            "mime_type": mime_type or "image/png"
        })
    
    return content_blocks


def test_basic_orchestrator_run():
    """Test basic orchestrator run functionality."""
    print("\n" + "="*60)
    print("Testing Basic Orchestrator Run")
    print("="*60)
    
    try:
        # Initialize orchestrator
        print(f"Initializing orchestrator at {datetime.now()}")
        orchestrator = Orchestrator()
        print(f"Orchestrator initialized at {datetime.now()}")
        
        # Create multimodal message with image
        image_path = "test.png"
        user_text = "I want to translate text in an image from japanese to English, return the translated image replacing the original text. Write it into same directory as the image but named test_translated.png."
        
        content_blocks = create_image_content_block(image_path, user_text)
        
        if not content_blocks:
            print(f"Warning: Test image not found at {image_path}")
            # Fallback to text-only message
            multimodal_message = HumanMessage(content=user_text)
        else:
            multimodal_message = HumanMessage(content=content_blocks)
        
        print(f"Running orchestrator with multimodal message at {datetime.now()}")
        result = orchestrator.run(messages=[multimodal_message], thread_id="test_basic")
        
        print(f"Orchestrator run completed at {datetime.now()}")
        print(f"Result keys: {list(result.keys())}")
        
        # Check if result has expected structure
        if "interrupted" in result:
            print(f"✓ Flow was interrupted (expected for feedback)")
            print("  Result (without all_paths):")
            filtered_result = {k: v for k, v in result.items() if k != "all_paths"}
            # print(pretty(filtered_result))
            print(f"  State keys: {list(result.get('state', {}).keys())}")
            print(f"  Next node: {result.get('next_node')}")
        else:
            print(f"✓ Flow completed successfully")
            print("  Result (without all_paths):")
            filtered_result = {k: v for k, v in result.items() if k != "all_paths"}
            print(pretty(filtered_result))
            print(f"  Response: {result.get('response', 'No response')}")
            print(f"  Is complete: {result.get('is_complete', False)}")
            print(f"  Next node: {result.get('next_node')}")
        
        return result
        
    except Exception as e:
        print(f"✗ Basic orchestrator test failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_orchestrator_with_message_history():
    """Test orchestrator with existing message history."""
    print("\n" + "="*60)
    print("Testing Orchestrator with Message History")
    print("="*60)
    
    try:
        orchestrator = Orchestrator()
        
        # Create message history (example conversation with structured metadata)
        message_history = [
            HumanMessage(
                content=(
                    "I want to translate text in an image from japanese to English, "
                    "return the translated image replacing the original text"
                )
            ),
            AIMessage(
                content=(
                    "User wants to translate Japanese text in an image to English and "
                    "replace the original text in the image.\n"
                    "The input is an image file.\n"
                    "The output should be an image file with the Japanese text replaced by English.\n"
                    "This requires OCR, translation, and image editing.\n"
                    "Thus the task is complex.\n"
                    "No ambiguity remains about the desired output format."
                ),
                response_metadata={
                    "clarification_question": None,
                    "cot": (
                        "User wants to translate Japanese text in an image to English and replace the original text in the image.\n"
                        "The input is an image file.\n"
                        "The output should be an image file with the Japanese text replaced by English.\n"
                        "This requires OCR, translation, and image editing.\n"
                        "Thus the task is complex.\n"
                        "No ambiguity remains about the desired output format."
                    ),
                    "input_type": "imagefile",
                    "is_complex": True,
                    "node": "classify",
                    "objective": "translate_japanese_text_in_image_to_english_and_replace_in_image",
                    "output_type": "imagefile",
                    "reasoning": (
                        "The user wants to take an image containing Japanese text, extract that text, translate it to English, "
                        "and then produce a new image where the original Japanese text is replaced by the English translation. "
                        "This requires OCR to read the Japanese text, machine translation to convert it to English, and image editing "
                        "to overlay the translated text onto the image while preserving layout and style. All of these steps involve "
                        "specialized processing beyond a simple text query, so the task is complex."
                    ),
                },
            ),
            AIMessage(
                content=("Could you please provide the image file you want to translate?"),
                response_metadata={
                    "clarification_question": "Could you please provide the image file you want to translate?",
                    "cot": (
                        "User wants Japanese→English translation in an image and replacement of original text.\n"
                        "We need OCR, translation, erase, and inpaint_text.\n"
                        "But no image path is given.\n"
                        "We must ask for the image file before selecting a path."
                    ),
                    "node": "route",
                    "path": [],
                    "reasoning": (
                        "The user wants to translate Japanese text in an image to English and replace the original text in the image. "
                        "This requires OCR, translation, erasing the original text, and inpainting the translated text. However, the user "
                        "has not provided the image file to process. Therefore, we cannot proceed with a concrete execution path until we "
                        "receive the image."
                    ),
                },
            ),
        ]
        # Create multimodal message with image
        image_path = r"C:\Users\Jacob\Documents\GitHub\Genesis\test.png"
        user_text = "yes, here is the image"
        
        content_blocks = create_image_content_block(image_path, user_text)
        
        if not content_blocks:
            # Fallback to text-only
            new_message = HumanMessage(content=user_text)
        else:
            new_message = HumanMessage(content=content_blocks)
        
        # Combine with message history
        all_messages = message_history + [new_message]
        
        print(f"Running orchestrator with message history at {datetime.now()}")
        result = orchestrator.run(
            messages=all_messages,
            thread_id="test_history"
        )
        
        print(f"✓ Orchestrator with history completed")
        print(f"  Result: {result}")
        print(f"  Messages in final state: {len(result.get('messages', []))}")
        
        return result
        
    except Exception as e:
        print(f"✗ Message history test failed: {e}")
        print(f"  Result: {result}")
        import traceback
        traceback.print_exc()
        return None


def test_orchestrator_feedback_flow():
    """Test orchestrator feedback and resume functionality."""
    print("\n" + "="*60)
    print("Testing Orchestrator Feedback Flow")
    print("="*60)
    
    try:
        orchestrator = Orchestrator()
        
        # Start with an ambiguous request that should trigger feedback
        user_input = "Process my image"
        thread_id = "test_feedback"
        
        print(f"Starting with ambiguous input at {datetime.now()}")
        messages = orchestrator.build_messages(user_input=user_input)
        result = orchestrator.run(messages=messages, thread_id=thread_id)
        
        if result.get("interrupted"):
            print(f"✓ Flow interrupted for clarification")
            print(f"  Question: {result.get('state', {}).get('classify_clarification')}")
            
            # Provide feedback
            feedback = "I want to extract Korean text from the image and translate it to English"
            print(f"Providing feedback: '{feedback}'")
            
            resume_result = orchestrator.resume_with_feedback(feedback, thread_id)
            print(f"✓ Resume completed")
            print(f"  Result: {resume_result}")
            print(f"  Final result keys: {list(resume_result.keys())}")
            
            return resume_result
        else:
            print(f"✗ Expected interruption but flow completed")
            return result
        
    except Exception as e:
        print(f"✗ Feedback flow test failed: {e}")
        print(f"  Result: {resume_result}")
        import traceback
        traceback.print_exc()
        return None


def test_orchestrator_different_scenarios():
    """Test orchestrator with different input scenarios."""
    print("\n" + "="*60)
    print("Testing Different Input Scenarios")
    print("="*60)
    
    scenarios = [
        {
            "name": "Image OCR",
            "input": "Extract text from my image using OCR",
            "thread_id": "test_ocr"
        },
        {
            "name": "Image Translation",
            "input": "Translate the text in my Korean image to English",
            "thread_id": "test_translation"
        },
        {
            "name": "Image Text Removal",
            "input": "Remove all text from my image",
            "thread_id": "test_removal"
        },
        {
            "name": "Complex Pipeline",
            "input": "Extract Korean text from image, translate to English, remove original text, and add translated text back",
            "thread_id": "test_complex"
        }
    ]
    
    results = {}
    orchestrator = Orchestrator()
    
    for scenario in scenarios:
        try:
            print(f"\n--- Testing: {scenario['name']} ---")
            print(f"Input: {scenario['input']}")
            
            messages = orchestrator.build_messages(user_input=scenario['input'])
            result = orchestrator.run(
                messages=messages,
                thread_id=scenario['thread_id']
            )
            
            results[scenario['name']] = result
            
            if result.get("interrupted"):
                print(f"  Status: Interrupted for feedback")
            else:
                print(f"  Status: Completed")
                print(f"  Response length: {len(result.get('response', ''))}")
            
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            print(f"  Result: {result}")
            results[scenario['name']] = {"error": str(e)}
    
    return results


def test_orchestrator_state_persistence():
    """Test that orchestrator maintains state across calls."""
    print("\n" + "="*60)
    print("Testing State Persistence")
    print("="*60)
    
    try:
        orchestrator = Orchestrator()
        thread_id = "test_persistence"
        
        # First call
        print("Making first call...")
        messages1 = orchestrator.build_messages(user_input="I have an image with Korean text")
        result1 = orchestrator.run(
            messages=messages1,
            thread_id=thread_id
        )
        print(f"  Result: {result1}")
        # Second call with same thread_id to continue conversation
        print("Making second call with same thread...")
        messages2 = orchestrator.build_messages(user_input="I want to translate it to English")
        result2 = orchestrator.run(
            messages=messages2,
            thread_id=thread_id
        )
        print(f"  Result: {result2}")
        print(f"✓ State persistence test completed")
        print(f"  Result: {result2}")
        print(f"  First result interrupted: {result1.get('interrupted', False)}")
        print(f"  Second result interrupted: {result2.get('interrupted', False)}")
        
        return {"first": result1, "second": result2}
        
    except Exception as e:
        print(f"✗ State persistence test failed: {e}")
        print(f"  Result: {result1}")
        print(f"  Result: {result2}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Main test execution."""
    print(f"Starting orchestrator tests at {datetime.now()}")
    
    # Set project root environment variable
    os.environ["GENESIS_PROJECT_ROOT"] = str(Path(__file__).parent.parent)
    
    test_results = {}
    
    # Run all tests
    print("Running comprehensive orchestrator tests...")
    
    test_results["basic"] = test_basic_orchestrator_run()
    # test_results["message_history"] = test_orchestrator_with_message_history()
    # test_results["feedback_flow"] = test_orchestrator_feedback_flow()
    # test_results["scenarios"] = test_orchestrator_different_scenarios()
    # test_results["persistence"] = test_orchestrator_state_persistence()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, result in test_results.items():
        if result is not None:
            print(f"✓ {test_name}: PASSED")
        else:
            print(f"✗ {test_name}: FAILED")
    
    print(f"\nAll tests completed at {datetime.now()}")
    
    return test_results


if __name__ == "__main__":
    main() 