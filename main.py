#!/usr/bin/env python3
"""
Genesis Main Application
========================

Main entry point for the Genesis AI assistant that provides a continuous 
chat interface with multimodal file upload capabilities using LangChain's 
content blocks.

Features:
- Continuous conversation loop
- Multimodal file upload (images, audio, documents, video)
- Pretty-printed responses
- Command history
- Graceful error handling
"""

import os
import sys
import mimetypes
import base64
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
import traceback

# Ensure proper encoding for Windows console
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Ensure project root is in sys.path
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import after path setup
from src.orchestrator import Orchestrator
from src.logging_utils import get_logger, pretty
from langchain_core.messages import HumanMessage, AIMessage


class GenesisApp:
    """Main Genesis application with chat loop and multimodal file handling."""
    
    def __init__(self):
        """Initialize the Genesis application."""
        self.logger = get_logger(__name__)
        self.orchestrator = Orchestrator()
        self.conversation_history = []
        self.thread_id = f"main_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        print("🚀 Genesis AI Assistant")
        print("=" * 50)
        print("Welcome! I can help you process files and answer questions.")
        print("Commands:")
        print("  /upload <file_path> - Upload a file")
        print("  /clear - Clear conversation history")
        print("  /help - Show this help")
        print("  /quit or /exit - Exit the application")
        print("=" * 50)
    
    def get_file_mime_type(self, file_path: str) -> Optional[str]:
        """Get MIME type for a file."""
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type
    
    def read_file_as_base64(self, file_path: str) -> str:
        """Read file and encode as base64."""
        with open(file_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def create_content_block(self, file_path: str) -> Dict[str, Any]:
        """
        Create a LangChain content block for a file based on its type.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Content block dictionary following LangChain v1 format
        """
        file_path = Path(file_path).resolve()
        mime_type = self.get_file_mime_type(str(file_path))
        
        # Determine content block type based on MIME type
        if mime_type:
            if mime_type.startswith('image/'):
                return {
                    "type": "image",
                    "base64": self.read_file_as_base64(str(file_path)),
                    "mime_type": mime_type
                }
            elif mime_type.startswith('audio/'):
                return {
                    "type": "audio", 
                    "data": self.read_file_as_base64(str(file_path)),
                    "mime_type": mime_type
                }
            elif mime_type.startswith('video/'):
                return {
                    "type": "video",
                    "data": self.read_file_as_base64(str(file_path)),
                    "mime_type": mime_type
                }
            elif mime_type == 'application/pdf':
                return {
                    "type": "file",
                    "data": self.read_file_as_base64(str(file_path)),
                    "mime_type": mime_type
                }
            elif mime_type.startswith('text/'):
                # For text files, read as text content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return {
                    "type": "text-plain",
                    "text": content,
                    "mime_type": mime_type
                }
        
        # Default to generic file type
        return {
            "type": "file",
            "data": self.read_file_as_base64(str(file_path)),
            "mime_type": mime_type or "application/octet-stream"
        }
    
    def upload_and_chat(self, file_paths: List[str], user_text: str = "") -> bool:
        """
        Upload files and optionally include text in a multimodal message.
        
        Args:
            file_paths: List of file paths to upload
            user_text: Optional text to include with the files
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create content blocks for all files
            content_blocks = []
            
            # Add text content if provided
            if user_text.strip():
                content_blocks.append({
                    "type": "text",
                    "text": user_text
                })
            
            # Add file content blocks
            valid_files = []
            for file_path in file_paths:
                file_path_obj = Path(file_path).resolve()
                
                if not file_path_obj.exists():
                    print(f"❌ File not found: {file_path}")
                    continue
                
                if not file_path_obj.is_file():
                    print(f"❌ Path is not a file: {file_path}")
                    continue
                
                try:
                    content_block = self.create_content_block(str(file_path_obj))
                    content_blocks.append(content_block)
                    valid_files.append(file_path_obj)
                    
                    size_mb = file_path_obj.stat().st_size / (1024 * 1024)
                    print(f"✅ Uploaded: {file_path_obj.name} ({size_mb:.2f} MB)")
                    if content_block.get("mime_type"):
                        print(f"   Type: {content_block['mime_type']}")
                        
                except Exception as e:
                    print(f"❌ Error reading {file_path}: {e}")
                    continue
            
            if not content_blocks:
                print("❌ No valid files or content to process")
                return False
            
            # Create multimodal message
            multimodal_message = HumanMessage(content=content_blocks)
            
            # Process with orchestrator
            print("🤖 Genesis: Processing your files...")
            
            result = self.orchestrator.run(
                messages=[multimodal_message],
                thread_id=self.thread_id
            )
            
            # Format and display response
            response = self.format_response(result)
            print(f"🤖 Genesis: {response}")
            
            # Update conversation history
            self.conversation_history.append(multimodal_message)
            self.conversation_history.append(AIMessage(content=response))
            
            # Handle clarification requests specifically
            if self.has_clarification_request(result):
                print("\n💡 Tip: Provide the requested information to continue.")
            
            return True
            
        except Exception as e:
            print(f"❌ Error processing files: {e}")
            self.logger.error(f"File processing error: {e}")
            return False
    
    def clear_conversation(self):
        """Clear conversation history."""
        self.conversation_history.clear()
        print("🧹 Conversation history cleared.")
    
    def show_help(self):
        """Show help information."""
        print("\n📖 Genesis AI Assistant Help")
        print("-" * 30)
        print("Commands:")
        print("  /upload <file_path> [text] - Upload a file with optional text")
        print("  /clear - Clear conversation history")
        print("  /help - Show this help message")
        print("  /quit or /exit - Exit the application")
        print("\nFile Support:")
        print("  • Images: jpg, png, gif, bmp, tiff, webp, svg")
        print("  • Audio: mp3, wav, flac, m4a, ogg, aac")
        print("  • Documents: pdf, txt, md, csv, json, xml")
        print("  • Video: mp4, avi, mkv, mov, wmv")
        print("\nExamples:")
        print("  /upload C:\\Users\\You\\image.png Translate this image")
        print("  'Extract the audio from this video file'")
        print("  'What programming language is this code written in?'")
        print("-" * 30)
    
    def process_command(self, user_input: str) -> bool:
        """
        Process a command (starts with /).
        
        Args:
            user_input: The user input starting with /
            
        Returns:
            True if command was processed, False if should exit
        """
        parts = user_input.strip().split()
        command = parts[0].lower()
        
        if command in ["/quit", "/exit"]:
            print("👋 Goodbye!")
            return False
        
        elif command == "/help":
            self.show_help()
        
        elif command == "/clear":
            self.clear_conversation()
        
        elif command == "/upload":
            if len(parts) < 2:
                print("❌ Usage: /upload <file_path> [optional text]")
            else:
                # First argument is file path, rest is optional text
                file_path = parts[1]
                text = " ".join(parts[2:]) if len(parts) > 2 else ""
                self.upload_and_chat([file_path], text)
        
        else:
            print(f"❌ Unknown command: {command}")
            print("💡 Type /help for available commands")
        
        return True
    
    def has_clarification_request(self, result: Dict[str, Any]) -> bool:
        """
        Check if the result contains a clarification request from agents.
        
        Args:
            result: The result from orchestrator.run()
            
        Returns:
            True if there are clarification questions requiring user input
        """
        state = result.get("state", {})
        return bool(state.get("classify_clarification") or state.get("route_clarification"))
    
    def format_response(self, result: Dict[str, Any]) -> str:
        """
        Format the orchestrator response for display.
        
        Args:
            result: The result from orchestrator.run()
            
        Returns:
            Formatted response string
        """
        # Check for clarification questions first (whether interrupted or not)
        state = result.get("state", {})
        
        # Handle clarification questions from agents
        if state.get("classify_clarification"):
            return f"❓ {state['classify_clarification']}"
        elif state.get("route_clarification"):
            return f"❓ {state['route_clarification']}"
        
        # Handle normal completion
        elif result.get("response"):
            response = result["response"]
            
            # Add execution summary if available
            exec_results = result.get("execution_results")
            if exec_results and isinstance(exec_results, dict):
                if exec_results.get("success"):
                    response += f"\n\n✅ Task completed successfully!"
                    if exec_results.get("final_output"):
                        response += f"\n📎 Output: {exec_results['final_output']}"
                else:
                    response += f"\n\n❌ Task encountered an error."
                    if exec_results.get("error_info"):
                        response += f"\n🔍 Error: {exec_results['error_info']}"
            
            return response
        
        # Handle interrupted flows (errors, exceptions)
        elif result.get("interrupted"):
            # Show actual error details when available
            error_msg = result.get("error")  # Top-level error from orchestrator
            if not error_msg:
                # Check for error details in state
                error_msg = state.get("error_details")
            
            if error_msg:
                return f"❌ An error occurred: {error_msg}"
            else:
                return "⚠️ The processing was interrupted unexpectedly. Please try again."
        
        # Handle malformed or unexpected results (shouldn't happen in normal operation)
        # This would only trigger if orchestrator returns a result without:
        # - clarification questions, AND
        # - response field, AND  
        # - interrupted flag
        else:
            return "🤔 Received an unexpected response format. Please try again or check the system status."
    
    def run_chat_loop(self):
        """Run the main chat loop."""
        print("\n💬 Chat started! Type your message or use commands (/help for options)")
        
        while True:
            try:
                # Get user input
                user_input = input("\n👤 You: ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    if not self.process_command(user_input):
                        break  # Exit command
                    continue
                
                # Process text-only input with orchestrator
                print("🤖 Genesis: Thinking...")
                
                # Build messages from user input and history
                messages = self.orchestrator.build_messages(
                    user_input=user_input,
                    message_history=self.conversation_history
                )
                
                result = self.orchestrator.run(
                    messages=messages,
                    thread_id=self.thread_id
                )
                
                # Format and display response
                response = self.format_response(result)
                print(f"🤖 Genesis: {response}")
                
                # Update conversation history
                self.conversation_history.append(HumanMessage(content=user_input))
                self.conversation_history.append(AIMessage(content=response))
                
                # Handle clarification requests specifically
                if self.has_clarification_request(result):
                    print("\n💡 Tip: Provide the requested information to continue.")
                
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                break
            
            except Exception as e:
                print(f"\n❌ An error occurred: {e}")
                self.logger.error(f"Chat loop error: {e}")
                self.logger.debug(traceback.format_exc())
                print("💡 You can continue chatting or type /quit to exit.")
    
    def run(self):
        """Run the Genesis application."""
        try:
            self.run_chat_loop()
        except Exception as e:
            print(f"\n💥 Fatal error: {e}")
            self.logger.error(f"Fatal application error: {e}")
            self.logger.debug(traceback.format_exc())
            sys.exit(1)


def main():
    """Main entry point."""
    # Set up environment
    os.environ.setdefault("GENESIS_PROJECT_ROOT", PROJECT_ROOT)
    
    # Run the app
    app = GenesisApp()
    app.run()


if __name__ == "__main__":
    main()