"""
Example of how to use the feedback functionality in the Genesis Orchestrator.

Based on LangGraph interrupt/resume pattern:
https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/wait-user-input/#simple-usage
"""

from src.orchestrator import Orchestrator

def main():
    # Initialize orchestrator
    orchestrator = Orchestrator()
    
    # Start conversation
    user_input = "Translate this image to Spanish"
    thread_id = "conversation_1"
    
    print(f"User: {user_input}")
    
    # Run initial request
    result = orchestrator.run(user_input, thread_id=thread_id)
    
    # Check if we hit an interrupt (need feedback)
    if result.get("interrupted"):
        print(f"\n🤔 System needs clarification:")
        print(f"Question: {result['state'].get('classify_clarification') or result['state'].get('route_clarification')}")
        
        # Simulate user providing feedback
        user_feedback = input("\nYour response: ")
        
        # Handle empty feedback - keep asking
        while not user_feedback.strip():
            print("Please provide a response to continue.")
            user_feedback = input("Your response: ")
        
        print(f"\n✅ User feedback: {user_feedback}")
        
        # Resume with feedback
        final_result = orchestrator.resume_with_feedback(user_feedback, thread_id=thread_id)
        
        # Check if we hit another interrupt
        while final_result.get("interrupted"):
            print(f"\n🤔 System needs more clarification:")
            print(f"Question: {final_result['state'].get('classify_clarification') or final_result['state'].get('route_clarification')}")
            
            user_feedback = input("\nYour response: ")
            while not user_feedback.strip():
                print("Please provide a response to continue.")
                user_feedback = input("Your response: ")
            
            print(f"\n✅ User feedback: {user_feedback}")
            final_result = orchestrator.resume_with_feedback(user_feedback, thread_id=thread_id)
        
        print(f"\n🎉 Final result: {final_result.get('response', 'Task completed!')}")
    else:
        print(f"\n🎉 Completed without interruption: {result.get('response', 'Task completed!')}")

def programmatic_example():
    """Example showing programmatic handling of feedback."""
    orchestrator = Orchestrator()
    
    # Start conversation
    result = orchestrator.run("Translate this image", thread_id="prog_example")
    
    # Handle feedback programmatically
    if result.get("interrupted"):
        # Provide feedback programmatically
        feedback = "Translate to French"
        print(f"Providing feedback: {feedback}")
        
        final_result = orchestrator.resume_with_feedback(feedback, thread_id="prog_example")
        print(f"Final result: {final_result}")

if __name__ == "__main__":
    print("=== Interactive Example ===")
    main()
    
    print("\n" + "="*50)
    print("=== Programmatic Example ===") 
    programmatic_example()
