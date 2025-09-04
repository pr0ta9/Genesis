import os
import sys
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from langchain_core.messages import AIMessage, HumanMessage
from src.agents.classifier import ClassificationResponse
from typing import Any

# Example 1: What the LLM returns as structured response
classification_result = ClassificationResponse(
    objective="solve_math_problems_in_pdf",
    input_type="documentfile",
    output_type="documentfile",
    is_complex=True,
    reasoning="User has PDF with math problems requiring document processing and mathematical computation",
    cot="""Let me analyze this step by step.
The user mentions they have a PDF file.
This PDF contains math problems that need to be solved.
They want solutions, not just text extraction.
This requires document parsing capabilities.
It also requires mathematical computation.
The output should be a solved/annotated version of the document.
This is clearly a complex task requiring multiple processing steps.""",
    clarification_question=None
)

# Example 2: How create_response_message would be called
def create_response_message(structured_response, user_response: str, **additional_metadata: Any) -> AIMessage:
    """
    Create an AIMessage with internal reasoning stored in metadata.
    """
    # Convert structured response to dict for storage
    internal_data = internal_data = structured_response.model_dump() if hasattr(structured_response, 'model_dump') else dict(structured_response)
    
    # Add any additional metadata
    internal_data.update(additional_metadata)
    print("internal_data")
    print(internal_data)
    return AIMessage(
        content=internal_data.get("response", internal_data.get("cot", "")),
        response_metadata=internal_data,
    )

# Example 3: Creating the response message
user_facing_text = "I can help you solve those math problems in your PDF. This looks like a complex task that will require multiple steps."

response_message = create_response_message(
    structured_response=classification_result,
    user_response=user_facing_text,
    node="classify",
    timestamp="2024-01-15T10:30:00Z"
)
messages = [response_message] + [HumanMessage(content="I have a PDF with calculus problems")]
print(messages)

# Example 4: What the AIMessage looks like
print("=== WHAT USER SEES ===")
print(f"Content: {response_message.content}")

print("\n=== WHAT SYSTEM STORES ===")
print("additional_kwargs:", response_message.additional_kwargs)

# Example 5: What gets stored in metadata
stored_data = response_message.response_metadata
print(f"\nStored objective: {stored_data['objective']}")
print(f"Stored CoT: {stored_data['cot']}")
print(f"Stored reasoning: {stored_data['reasoning']}")
print(f"Additional metadata node: {stored_data['node']}")

# Example 6: What the next LLM call would see
def prepare_for_next_llm_call(messages):
    """Example of how messages would be prepared for next LLM call"""
    reconstructed = []
    for msg in messages:
        if isinstance(msg, AIMessage) and "agent_reasoning" in msg.additional_kwargs:
            reasoning = msg.additional_kwargs["agent_reasoning"]
            cot = reasoning.get("cot", "")
            
            # Show CoT to LLM
            if cot:
                llm_content = f"{cot}\n\n{msg.content}"
                reconstructed.append(AIMessage(content=llm_content))
            else:
                reconstructed.append(msg)
        else:
            reconstructed.append(msg)
    return reconstructed

# Example 7: The complete message flow
example_messages = [
    HumanMessage(content="I have a PDF with calculus problems"),
    response_message  # The AIMessage we just created
]

print("\n=== WHAT NEXT LLM WOULD SEE ===")
llm_ready_messages = prepare_for_next_llm_call(example_messages)
for i, msg in enumerate(llm_ready_messages):
    print(f"Message {i+1} ({type(msg).__name__}):")
    print(msg.content)
    print("-" * 50)
print("\n=== WHAT NEXT LLM WOULD SEE ===")
print(response_message)

# Example output would be:
# Message 1 (HumanMessage):
# I have a PDF with calculus problems
# --------------------------------------------------
# Message 2 (AIMessage):
# Let me analyze this step by step.
# The user mentions they have a PDF file.
# This PDF contains math problems that need to be solved.
# They want solutions, not just text extraction.
# This requires document parsing capabilities.
# It also requires mathematical computation.
# The output should be a solved/annotated version of the document.
# This is clearly a complex task requiring multiple processing steps.
# 
# I can help you solve those math problems in your PDF. This looks like a complex task that will require multiple steps.
# --------------------------------------------------