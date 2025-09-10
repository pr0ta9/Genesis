#!/usr/bin/env python3
"""
CLI Test for Agent Streaming with Reasoning
Tests the _stream_invoke method with real agents before GUI integration
"""

import sys
import os
import asyncio
from typing import List
from langchain_core.messages import HumanMessage, SystemMessage

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents import setup_llm
from src.agents.classifier import Classifier
from src.agents.router import Router
from src.agents.finalizer import Finalizer
from src.orchestrator import Orchestrator
from src.state import State
from langchain_core.messages import HumanMessage


class StreamingTester:
    """CLI tester for agent streaming functionality"""
    
    def __init__(self):
        # Set up LLM (same as orchestrator)
        self.llm = setup_llm("ollama", "gpt-oss:20b")
        
        # Initialize agents
        self.classifier = Classifier(self.llm)        
        self.router = Router(self.llm)
        self.finalizer = Finalizer(self.llm)
        
        # Initialize orchestrator for full workflow testing
        self.orchestrator = Orchestrator()
        
        print("🔧 StreamingTester initialized with agents")
        print(f"   - Classifier: {type(self.classifier).__name__}")
        print(f"   - Router: {type(self.router).__name__}")
        print(f"   - Finalizer: {type(self.finalizer).__name__}")
    
    def test_classifier_streaming(self):
        """Test classifier with streaming reasoning"""
        print("\n" + "="*60)
        print("🧪 TESTING CLASSIFIER STREAMING")
        print("="*60)
        
        # Create test messages
        messages = [
            HumanMessage(content="I need to convert a PDF document to text and then translate it to Spanish")
        ]
        
        print("📝 Input: Convert PDF to text and translate to Spanish")
        print("🔄 Starting classifier streaming...")
        print("-" * 40)
        
        reasoning_chunks = []
        final_result = None
        
        try:
            # Use the new streaming method
            for update_type, content in self.classifier._stream_invoke(
                messages=messages,
                node="classify_test",
            ):
                if update_type == "reasoning":
                    reasoning_chunks.append(content)
                    print(f"💭 [REASONING #{len(reasoning_chunks)}]: {content[:100]}...")
                    
                elif update_type == "result":
                    structured_result, updated_messages = content
                    final_result = structured_result
                    print(f"✅ [RESULT]: {type(structured_result).__name__}")
                    break
            
            print("-" * 40)
            print(f"📊 Summary:")
            print(f"   - Reasoning chunks received: {len(reasoning_chunks)}")
            print(f"   - Final result type: {type(final_result)}")
            
            if final_result:
                if hasattr(final_result, 'model_dump'):
                    result_dict = final_result.model_dump()
                    print(f"   - Objective: {result_dict.get('objective', 'N/A')}")
                    print(f"   - Input type: {result_dict.get('input_type', 'N/A')}")
                    print(f"   - Output type: {result_dict.get('output_type', 'N/A')}")
                    print(f"   - Is complex: {result_dict.get('is_complex', 'N/A')}")
                else:
                    print(f"   - Result: {final_result}")
            
            return len(reasoning_chunks) > 0, final_result
            
        except Exception as e:
            print(f"❌ Error during classifier streaming: {e}")
            import traceback
            traceback.print_exc()
            return False, None
    
    def test_router_streaming(self):
        """Test router with streaming reasoning"""
        print("\n" + "="*60)
        print("🧪 TESTING ROUTER STREAMING")
        print("="*60)
        
        # Create test state (simulate what comes from classifier)
        messages = [
            HumanMessage(content="Convert this image to text using OCR"),
        ]
        
        # Create mock state for router
        test_state = {
            "messages": messages,
            "objective": "Convert image to text using OCR",
            "input_type": "image",
            "output_type": "text", 
            "is_complex": False,
            "all_paths": [
                [{"name": "image_ocr", "description": "Convert image to text using OCR"}],
                [{"name": "image_to_text", "description": "Alternative image to text conversion"}]
            ],
            "tool_metadata": [
                {"name": "image_ocr", "description": "Convert image to text using OCR"},
                {"name": "image_to_text", "description": "Alternative image to text conversion"}
            ]
        }
        
        print("📝 Input: Router decision for OCR task")
        print("🔄 Starting router streaming...")
        print("-" * 40)
        
        reasoning_chunks = []
        final_result = None
        
        try:
            # Use the new streaming method with state context
            for update_type, content in self.router._stream_invoke(
                messages=messages,
                node="route_test",
                **test_state  # Pass state as template variables
            ):
                if update_type == "reasoning":
                    reasoning_chunks.append(content)
                    print(f"💭 [REASONING #{len(reasoning_chunks)}]: {content[:100]}...")
                    
                elif update_type == "result":
                    structured_result, updated_messages = content
                    final_result = structured_result
                    print(f"✅ [RESULT]: {type(structured_result).__name__}")
                    break
            
            print("-" * 40)
            print(f"📊 Summary:")
            print(f"   - Reasoning chunks received: {len(reasoning_chunks)}")
            print(f"   - Final result type: {type(final_result)}")
            
            if final_result:
                if hasattr(final_result, 'model_dump'):
                    result_dict = final_result.model_dump()
                    print(f"   - Chosen path: {result_dict.get('chosen_path', 'N/A')}")
                    print(f"   - Reasoning: {result_dict.get('reasoning', 'N/A')[:100]}...")
                else:
                    print(f"   - Result: {final_result}")
            
            return len(reasoning_chunks) > 0, final_result
            
        except Exception as e:
            print(f"❌ Error during router streaming: {e}")
            import traceback
            traceback.print_exc()
            return False, None
    
    def test_orchestrator_streaming(self):
        """Test full orchestrator with streaming for classify node"""
        print("\n" + "="*60)
        print("🧪 TESTING ORCHESTRATOR STREAMING")
        print("="*60)
        
        # Create test message
        messages = [
            HumanMessage(content="I need to extract text from a PDF document and then translate it to French")
        ]
        
        print("📝 Input: Extract text from PDF and translate to French")
        print("🔄 Starting orchestrator streaming...")
        print("-" * 40)
        
        reasoning_chunks = []
        node_completions = []
        final_result = None
        
        try:
            # Use the new streaming orchestrator method
            for update_type, content in self.orchestrator.run_with_streaming(
                messages=messages,
                thread_id="test_streaming_session"
            ):
                if update_type == "reasoning":
                    reasoning_chunks.append(content)
                    print(f"💭 [REASONING #{len(reasoning_chunks)}]: {content[:100]}...")
                    
                elif update_type == "node_complete":
                    node_name, node_result = content
                    node_completions.append((node_name, node_result))
                    print(f"✅ [NODE COMPLETE]: {node_name}")
                    
                    # Show key results
                    if node_name == "classify":
                        obj = node_result.get('objective', 'N/A')
                        inp = node_result.get('input_type', 'N/A')
                        out = node_result.get('output_type', 'N/A')
                        complex_task = node_result.get('is_complex', False)
                        print(f"    - Objective: {obj}")
                        print(f"    - Input→Output: {inp} → {out}")
                        print(f"    - Complex: {complex_task}")
                    
                elif update_type == "result":
                    final_result = content
                    print(f"🏁 [FINAL RESULT]: Orchestrator completed")
                    break
            
            print("-" * 40)
            print(f"📊 Orchestrator Streaming Summary:")
            print(f"   - Reasoning chunks received: {len(reasoning_chunks)}")
            print(f"   - Nodes completed: {len(node_completions)}")
            print(f"   - Final result available: {final_result is not None}")
            
            if final_result:
                if "error" in final_result:
                    print(f"   - Error: {final_result['error']}")
                elif "interrupted" in final_result:
                    print(f"   - Interrupted: {final_result.get('clarification', 'No clarification')}")
                else:
                    print(f"   - Status: Completed successfully")
                    print(f"   - Response: {final_result.get('response', 'N/A')[:100]}...")
            
            return len(reasoning_chunks) > 0, final_result
            
        except Exception as e:
            print(f"❌ Error during orchestrator streaming: {e}")
            import traceback
            traceback.print_exc()
            return False, None
    
    def test_all_agents(self):
        """Test all agents with streaming"""
        print("🚀 Starting comprehensive agent streaming test")
        print("="*60)
        
        results = {}
        
        # Test classifier
        reasoning_received, result = self.test_classifier_streaming()
        results['classifier'] = {
            'reasoning_received': reasoning_received,
            'result_available': result is not None
        }
        
        # Test router  
        reasoning_received, result = self.test_router_streaming()
        results['router'] = {
            'reasoning_received': reasoning_received,
            'result_available': result is not None
        }
        
        # Test orchestrator streaming
        reasoning_received, result = self.test_orchestrator_streaming()
        results['orchestrator'] = {
            'reasoning_received': reasoning_received,
            'result_available': result is not None
        }
        
        # Print final summary
        print("\n" + "="*60)
        print("🏁 FINAL TEST SUMMARY")
        print("="*60)
        
        for agent_name, agent_results in results.items():
            status = "✅" if all(agent_results.values()) else "❌"
            print(f"{status} {agent_name.title()}:")
            print(f"   - Reasoning received: {agent_results['reasoning_received']}")
            print(f"   - Result available: {agent_results['result_available']}")
        
        all_passed = all(
            all(agent_results.values()) 
            for agent_results in results.values()
        )
        
        if all_passed:
            print("\n🎉 All streaming tests passed! Ready for GUI integration.")
        else:
            print("\n⚠️  Some tests failed. Check the output above.")
        
        return all_passed


def run_interactive_test():
    """Run interactive streaming test"""
    tester = StreamingTester()
    
    print("🎮 Interactive Agent Streaming Test")
    print("Type 'quit' to exit\n")
    
    while True:
        user_input = input("👤 Enter a task description: ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("👋 Goodbye!")
            break
        
        if not user_input:
            continue
        
        print(f"\n🔄 Testing classifier streaming with: '{user_input}'")
        print("-" * 50)
        
        messages = [HumanMessage(content=user_input)]
        reasoning_count = 0
        
        try:
            for update_type, content in tester.classifier._stream_invoke(
                messages=messages,
                node="interactive_test",
            ):
                if update_type == "reasoning":
                    reasoning_count += 1
                    print(f"💭 [{reasoning_count}] {content}")
                    
                elif update_type == "result":
                    structured_result, _ = content
                    print(f"\n✅ Final classification:")
                    if hasattr(structured_result, 'model_dump'):
                        result_dict = structured_result.model_dump()
                        for key, value in result_dict.items():
                            if key != 'reasoning':  # Skip reasoning since we showed it above
                                print(f"   {key}: {value}")
                    break
                    
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("\n" + "="*50 + "\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test agent streaming functionality")
    parser.add_argument("--interactive", "-i", action="store_true", 
                       help="Run interactive test")
    parser.add_argument("--agent", "-a", choices=["classifier", "router", "orchestrator", "all"], 
                       default="all", help="Which agent/component to test")
    
    args = parser.parse_args()
    
    if args.interactive:
        run_interactive_test()
    else:
        tester = StreamingTester()
        
        if args.agent == "classifier":
            tester.test_classifier_streaming()
        elif args.agent == "router":
            tester.test_router_streaming()
        elif args.agent == "orchestrator":
            tester.test_orchestrator_streaming()
        else:
            tester.test_all_agents()
