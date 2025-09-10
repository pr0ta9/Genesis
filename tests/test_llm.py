import os
from typing import List, Tuple, Generator

from langchain_ollama import ChatOllama 


MODEL_NAME = "gpt-oss:20b"
llm = ChatOllama(model=MODEL_NAME, temperature=0.0, validate_model_on_init=True)



def stream_with_reasoning(llm: "ChatOllama", messages: List[Tuple[str, str]]) -> Tuple[str, str]:  # type: ignore[name-defined]
    full_text_parts: List[str] = []
    # Stream visible content tokens; reasoning is returned on the final message metadata
    for chunk in llm.stream(messages, reasoning=True):  # type: ignore[attr-defined]
        text = getattr(chunk, "content", "") or ""
        if not isinstance(text, str):
            continue
        print(text, end="", flush=True)
        full_text_parts.append(text)
    print()
    # Get final message to access reasoning_content
    final_msg = llm.invoke(messages, reasoning=True)  # type: ignore[attr-defined]
    reasoning_content = None
    if hasattr(final_msg, "additional_kwargs"):
        reasoning_content = final_msg.additional_kwargs.get("reasoning_content") or final_msg.additional_kwargs.get("reasoning")
    if reasoning_content is None and hasattr(final_msg, "response_metadata"):
        reasoning_content = final_msg.response_metadata.get("reasoning_content")
    return "".join(full_text_parts), (reasoning_content or "").strip()


def example_stream_reasoning():
    print("\n== Streaming with reasoning=True (no <think> tags) ==\n")
    messages: List[Tuple[str, str]] = [("human", "Briefly explain how a hash map works.")]
    final_text, reasoning = stream_with_reasoning(llm, messages)
    if reasoning:
        print("\n-- reasoning_content --\n" + reasoning)


def example_reasoning_true():
    print("\n== Reasoning=True example (separate reasoning_content) ==\n")
    llm = ChatOllama(
        model=MODEL_NAME,
        temperature=0.0,
        num_predict=128,
        # reasoning=True,
        validate_model_on_init=True,
    )

    result = llm.invoke([("human", "What is 17 + 28?")], reasoning=True)  # type: ignore[attr-defined]
    print(result)
    content = getattr(result, "content", "")
    reasoning_content = None
    if hasattr(result, "additional_kwargs"):
        reasoning_content = result.additional_kwargs.get("reasoning_content") or result.additional_kwargs.get("reasoning")
    if reasoning_content is None and hasattr(result, "response_metadata"):
        reasoning_content = result.response_metadata.get("reasoning_content")

    if reasoning_content:
        print("-- reasoning_content --\n" + str(reasoning_content).strip() + "\n")
    print("-- final content --\n" + str(content).strip() + "\n")


def test_streaming_with_reasoning_callback():
    """Test streaming reasoning with callback pattern (similar to base_agent approach)."""
    print("\n== Testing Streaming with Reasoning Callback ==\n")
    
    # Simulate the callback that would be used in GUI
    reasoning_chunks = []
    def reasoning_callback(reasoning_text):
        print(f"[REASONING CHUNK]: {reasoning_text}")
        reasoning_chunks.append(reasoning_text)
    
    # Create LLM with reasoning enabled
    llm = ChatOllama(
        model=MODEL_NAME,
        temperature=0.0,
        validate_model_on_init=False,
    )
    
    messages = [("human", "Explain how a binary search algorithm works step by step.")]
    
    # Stream with reasoning separation (simulating base_agent approach)
    main_content_buffer = ""
    final_reasoning = None
    
    print("Streaming response...")
    print("=" * 50)
    
    for chunk in llm.stream(messages, reasoning=True):
        # Handle reasoning content immediately (simulate real-time GUI update)
        if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
            reasoning_content = chunk.additional_kwargs.get('reasoning_content')
            if reasoning_content:
                reasoning_callback(reasoning_content)
                final_reasoning = reasoning_content
        
        # Buffer main content (simulate JSON accumulation)
        if hasattr(chunk, 'content') and chunk.content:
            main_content_buffer += chunk.content
            print(chunk.content, end="", flush=True)
    
    print("\n" + "=" * 50)
    
    # Final results
    print(f"\n-- Final Main Content ({len(main_content_buffer)} chars) --")
    print(main_content_buffer[:200] + "..." if len(main_content_buffer) > 200 else main_content_buffer)
    
    print(f"\n-- Reasoning Chunks Received: {len(reasoning_chunks)} --")
    if final_reasoning:
        print(f"Final reasoning content: {final_reasoning[:100]}...")
    
    print(f"\n-- Simulation Complete --")
    print(f"✓ Reasoning streamed in real-time: {len(reasoning_chunks) > 0}")
    print(f"✓ Main content buffered: {len(main_content_buffer) > 0}")
    
    return main_content_buffer, final_reasoning


def test_generator_streaming():
    """Test generator-based streaming that base_agent would use."""
    print("\n== Testing Generator-Based Streaming ==\n")
    
    def stream_invoke_generator(llm, messages, node="test_node"):
        """Generator that mimics base_agent._stream_invoke"""
        print(f"Starting stream for node: {node}")
        
        # Stream with reasoning
        main_content_buffer = ""
        for chunk in llm.stream(messages, reasoning=True):
            # Yield reasoning immediately
            if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
                reasoning_content = chunk.additional_kwargs.get('reasoning_content')
                if reasoning_content:
                    yield ("reasoning", reasoning_content)
            
            # Buffer main content
            if hasattr(chunk, 'content') and chunk.content:
                main_content_buffer += chunk.content
        
        # Yield final result
        yield ("result", {
            "structured_content": main_content_buffer,
            "node": node,
            "status": "completed"
        })
    
    # Create LLM
    llm = ChatOllama(
        model=MODEL_NAME,
        temperature=0.1,
        validate_model_on_init=False,
    )
    
    messages = [("human", "Explain quantum computing in simple terms.")]
    
    # Simulate GUI consuming the generator
    print("GUI starting to consume stream...")
    print("-" * 50)
    
    reasoning_updates = []
    final_result = None
    
    for update_type, content in stream_invoke_generator(llm, messages, "quantum_explanation"):
        if update_type == "reasoning":
            reasoning_updates.append(content)
            print(f"[GUI] Reasoning update #{len(reasoning_updates)}: {len(content)} chars")
            # Simulate GUI updating reasoning display
            print(f"[GUI] Current reasoning preview: {content[:100]}...")
            
        elif update_type == "result":
            final_result = content
            print(f"[GUI] Final result received!")
            print(f"[GUI] Content length: {len(content.get('structured_content', ''))} chars")
            break
    
    print("-" * 50)
    print(f"Stream complete!")
    print(f"Total reasoning updates: {len(reasoning_updates)}")
    print(f"Final result available: {final_result is not None}")
    
    if final_result:
        preview = final_result.get('structured_content', '')[:200]
        print(f"Content preview: {preview}...")
    
    return reasoning_updates, final_result


def test_base_agent_style_streaming():
    """Test streaming that mimics how base_agent would handle structured output."""
    print("\n== Testing Base Agent Style Streaming ==\n")
    
    # Track reasoning updates for GUI
    gui_reasoning_updates = []
    
    def gui_reasoning_handler(reasoning_text):
        """Simulate GUI receiving reasoning updates."""
        gui_reasoning_updates.append({
            "timestamp": len(gui_reasoning_updates),
            "content": reasoning_text
        })
        print(f"[GUI UPDATE {len(gui_reasoning_updates)}]: Reasoning received ({len(reasoning_text)} chars)")
    
    # Create LLM (simulating base_agent setup)
    llm = ChatOllama(
        model=MODEL_NAME,
        temperature=0.1,
        validate_model_on_init=False,
    )
    
    # Simulate a structured output scenario
    messages = [
        ("system", "You are a helpful assistant. Provide a detailed analysis."),
        ("human", "Analyze the pros and cons of renewable energy sources.")
    ]
    
    print("Starting streaming analysis...")
    print("-" * 40)
    
    # Streaming with reasoning separation
    content_buffer = ""
    complete_reasoning = None
    chunk_count = 0
    
    try:
        for chunk in llm.stream(messages, reasoning=True):
            chunk_count += 1
            
            # Process reasoning immediately (real-time GUI updates)
            if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
                reasoning = chunk.additional_kwargs.get('reasoning_content')
                if reasoning:
                    gui_reasoning_handler(reasoning)
                    complete_reasoning = reasoning
            
            # Accumulate main content (for structured parsing)
            if hasattr(chunk, 'content') and chunk.content:
                content_buffer += chunk.content
                print(".", end="", flush=True)  # Progress indicator
    
        print(f"\n{'-' * 40}")
        print(f"Streaming complete! Processed {chunk_count} chunks")
        
        # Simulate final processing (like base_agent would do)
        print(f"\n-- Final Results --")
        print(f"Main content length: {len(content_buffer)} characters")
        print(f"Reasoning updates sent to GUI: {len(gui_reasoning_updates)}")
        
        if complete_reasoning:
            print(f"Complete reasoning available: {len(complete_reasoning)} characters")
            print(f"Reasoning preview: {complete_reasoning[:150]}...")
        
        if content_buffer:
            print(f"Content preview: {content_buffer[:200]}...")
        
        # Simulate what base_agent would return
        return {
            "structured_content": content_buffer,
            "reasoning_content": complete_reasoning,
            "gui_updates_sent": len(gui_reasoning_updates)
        }
        
    except Exception as e:
        print(f"\nError during streaming: {e}")
        return None


def maybe_streamlit_demo():
    if os.getenv("LLM_STREAMLIT_DEMO") != "1":
        return
    try:
        import streamlit as st  # type: ignore
        try:
            from langchain_community.callbacks.streamlit import StreamlitCallbackHandler  # type: ignore
        except Exception:
            from langchain.callbacks.streamlit import StreamlitCallbackHandler  # type: ignore
    except Exception:
        return

    st.set_page_config(page_title="ChatOllama Reasoning Stream Demo", page_icon="🧠")
    st.title("ChatOllama Reasoning Stream Demo")
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat messages from history on app rerun
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Use reasoning=True here to let the handler show thought steps when supported
    llm = ChatOllama(
        model=MODEL_NAME,
        temperature=0.0,
        reasoning=True,
        validate_model_on_init=False,
    )

    # React to user input
    if prompt := st.chat_input("Ask me anything about reasoning or complex topics..."):
        # Display user message in chat message container
        st.chat_message("user").markdown(prompt)
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Display assistant response in chat message container
        with st.chat_message("assistant"):
            # Create StreamlitCallbackHandler for this response
            st_callback = StreamlitCallbackHandler(
                st.container(),
                expand_new_thoughts=True,
                collapse_completed_thoughts=True
            )
            
            # Get response with streaming callback
            try:
                response = llm.invoke(
                    [("human", prompt)], 
                    callbacks=[st_callback],
                    reasoning=True
                )
                
                # Display the main content
                st.write(response.content)
                
                # Show reasoning if available
                reasoning_content = None
                if hasattr(response, "additional_kwargs"):
                    reasoning_content = response.additional_kwargs.get("reasoning_content") or response.additional_kwargs.get("reasoning")
                if reasoning_content is None and hasattr(response, "response_metadata"):
                    reasoning_content = response.response_metadata.get("reasoning_content")
                
                if reasoning_content:
                    with st.expander("🧠 Reasoning Process", expanded=False):
                        st.text_area("Internal Reasoning:", reasoning_content, height=200, disabled=True)
                
                # Add assistant response to chat history
                st.session_state.messages.append({"role": "assistant", "content": response.content})
                
            except Exception as e:
                st.error(f"Error getting response: {str(e)}")
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {str(e)}"})

    # Sidebar with configuration
    with st.sidebar:
        st.header("Configuration")
        st.write(f"**Model:** {MODEL_NAME}")
        st.write(f"**Temperature:** 0.0")
        st.write(f"**Reasoning:** Enabled")
        
        if st.button("Clear Chat History"):
            st.session_state.messages = []
            st.rerun()
        
        st.header("About")
        st.write("This demo shows ChatOllama with reasoning capabilities using StreamlitCallbackHandler from LangChain.")
        st.write("The callback handler visualizes the model's thought process and reasoning steps.")


if __name__ == "__main__":
    # Console examples
    # example_stream_reasoning()
    # example_reasoning_true()
    
    # Test streaming approaches for base_agent integration
    # test_streaming_with_reasoning_callback()
    test_generator_streaming()
    # test_base_agent_style_streaming()

    # Optional Streamlit demo: set environment variable LLM_STREAMLIT_DEMO=1
    # maybe_streamlit_demo()
