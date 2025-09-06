# Multimodal Usage Guide for Genesis

This guide explains how to use Genesis with LangChain's multimodal content blocks for handling files and media directly within messages.

## Overview

Genesis now uses [LangChain's v1 multimodal content blocks](https://docs.langchain.com/oss/python/langchain-messages#multimodal) to handle files. Instead of separate file objects, files are embedded directly into messages as typed content blocks, providing better integration with LangChain's ecosystem.

## Interactive Chat Interface (`main.py`)

### Starting the Application

```bash
python main.py
```

### File Upload Commands

- **Upload a file with text**: `/upload <file_path> [optional text]`
- **Clear conversation**: `/clear`
- **Show help**: `/help`
- **Exit**: `/quit` or `/exit`

### Example Session

```
🚀 Genesis AI Assistant
==================================================
Welcome! I can help you process files and answer questions.

👤 You: /upload C:\Users\You\image.png Translate the Japanese text in this image to English
✅ Uploaded: image.png (1.23 MB)
   Type: image/png
🤖 Genesis: I'll help you translate the Japanese text in the uploaded image...

👤 You: Make the translated text larger
🤖 Genesis: I'll adjust the font size of the translated text...
```

## Programmatic Usage

### Basic Multimodal Message

```python
from src.orchestrator import Orchestrator
from langchain_core.messages import HumanMessage
import base64

# Read image file
with open("image.png", "rb") as f:
    image_data = base64.b64encode(f.read()).decode('utf-8')

# Create multimodal content
content_blocks = [
    {
        "type": "text",
        "text": "Translate the text in this image to English"
    },
    {
        "type": "image", 
        "base64": image_data,
        "mime_type": "image/png"
    }
]

# Create message and process
multimodal_message = HumanMessage(content=content_blocks)
orchestrator = Orchestrator()

result = orchestrator.run(
    messages=[multimodal_message],
    thread_id="translation_session"
)
```

### Helper Function for File Processing

```python
import mimetypes
import base64
from pathlib import Path

def create_content_blocks(file_path: str, text: str = ""):
    """Create LangChain content blocks from file and text."""
    content_blocks = []
    
    # Add text if provided
    if text.strip():
        content_blocks.append({
            "type": "text",
            "text": text
        })
    
    # Process file based on type
    file_path = Path(file_path)
    mime_type, _ = mimetypes.guess_type(str(file_path))
    
    with open(file_path, 'rb') as f:
        file_data = base64.b64encode(f.read()).decode('utf-8')
    
    if mime_type and mime_type.startswith('image/'):
        content_blocks.append({
            "type": "image",
            "base64": file_data,
            "mime_type": mime_type
        })
    elif mime_type and mime_type.startswith('audio/'):
        content_blocks.append({
            "type": "audio",
            "data": file_data,
            "mime_type": mime_type
        })
    elif mime_type and mime_type.startswith('video/'):
        content_blocks.append({
            "type": "video", 
            "data": file_data,
            "mime_type": mime_type
        })
    elif mime_type == 'application/pdf':
        content_blocks.append({
            "type": "file",
            "data": file_data,
            "mime_type": mime_type
        })
    elif mime_type and mime_type.startswith('text/'):
        # For text files, include content as text
        with open(file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
        content_blocks.append({
            "type": "text-plain",
            "text": text_content,
            "mime_type": mime_type
        })
    else:
        # Generic file
        content_blocks.append({
            "type": "file",
            "data": file_data,
            "mime_type": mime_type or "application/octet-stream"
        })
    
    return content_blocks
```

## Content Block Types

Genesis supports all LangChain v1 content block types, including reasoning blocks for AI chain-of-thought:

### Core Content Blocks

#### Text Content
```python
{
    "type": "text",
    "text": "Your text content here"
}
```

#### Reasoning Content (AI Chain-of-Thought)
```python
{
    "type": "reasoning",
    "reasoning": "Step-by-step thinking process from AI agents"
}
```

#### Plain Text Files
```python
{
    "type": "text-plain", 
    "text": "File content as text",
    "mime_type": "text/plain"
}
```

### Multimodal Content Blocks

#### Images
```python
{
    "type": "image",
    "base64": "iVBORw0KGgoAAAANSUhEUgAA...",  # base64 data
    "mime_type": "image/png"
}
```

#### Audio Files
```python
{
    "type": "audio",
    "data": "UklGRiQAAABXQVZFZm10...",  # base64 data
    "mime_type": "audio/wav"
}
```

#### Video Files
```python
{
    "type": "video",
    "data": "AAAAIGZ0eXBpc29tAAACAGlzb21pc28y...",  # base64 data
    "mime_type": "video/mp4"
}
```

#### Generic Files (PDFs, etc.)
```python
{
    "type": "file",
    "data": "JVBERi0xLjQKJcOkw7zDtsO...",  # base64 data
    "mime_type": "application/pdf"
}
```

## Supported File Types

| Type | Extensions | Content Block Type |
|------|------------|-------------------|
| Images | `.jpg`, `.png`, `.gif`, `.bmp`, `.webp`, `.tiff`, `.svg` | `image` |
| Audio | `.mp3`, `.wav`, `.flac`, `.m4a`, `.ogg`, `.aac` | `audio` |
| Video | `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.webm` | `video` |
| Documents | `.pdf` | `file` |
| Text | `.txt`, `.md`, `.csv`, `.json`, `.py`, `.js`, etc. | `text-plain` |

## Examples

### Image Translation
```python
content_blocks = [
    {"type": "text", "text": "Translate Korean text to English"},
    {"type": "image", "base64": image_data, "mime_type": "image/jpeg"}
]
message = HumanMessage(content=content_blocks)
```

### Document Analysis
```python
content_blocks = [
    {"type": "text", "text": "Summarize this document"},
    {"type": "file", "data": pdf_data, "mime_type": "application/pdf"}
]
message = HumanMessage(content=content_blocks)
```

### Audio Transcription
```python
content_blocks = [
    {"type": "text", "text": "Transcribe this audio"},
    {"type": "audio", "data": audio_data, "mime_type": "audio/mp3"}
]
message = HumanMessage(content=content_blocks)
```

### Code Analysis
```python
with open("script.py", "r") as f:
    code_content = f.read()

content_blocks = [
    {"type": "text", "text": "Review this Python code for bugs"},
    {"type": "text-plain", "text": code_content, "mime_type": "text/x-python"}
]
message = HumanMessage(content=content_blocks)
```

### Multiple Files
```python
content_blocks = [
    {"type": "text", "text": "Compare these files"},
    {"type": "image", "base64": image1_data, "mime_type": "image/png"},
    {"type": "image", "base64": image2_data, "mime_type": "image/png"}
]
message = HumanMessage(content=content_blocks)
```

## Advanced Usage

### Mixed Content Conversation
```python
# Message 1: Upload and analyze
message1 = HumanMessage(content=[
    {"type": "text", "text": "What's in this image?"},
    {"type": "image", "base64": image_data, "mime_type": "image/png"}
])

# Process first message
result1 = orchestrator.run(messages=[message1], thread_id="analysis")

# Message 2: Follow-up (text only)
message2 = HumanMessage(content="Can you enhance the colors?")

# Continue conversation
messages2 = orchestrator.build_messages(
    user_input="Can you enhance the colors?",
    message_history=[message1, AIMessage(content=result1["response"])]
)
result2 = orchestrator.run(messages=messages2, thread_id="analysis")
```

### File References in Conversation
Once a file is uploaded in a multimodal message, you can reference it in subsequent text messages:

```python
# Upload file
upload_message = HumanMessage(content=[
    {"type": "text", "text": "Here's my document"},
    {"type": "file", "data": pdf_data, "mime_type": "application/pdf"}
])

# Later reference the file
follow_up = "Can you create a summary of page 3 from the document I uploaded?"
```

## AI Reasoning Blocks

Genesis agents automatically include their chain-of-thought (cot) reasoning as `ReasoningContentBlock` objects in AI messages. This provides transparency into the AI's decision-making process.

### Automatic Reasoning Inclusion

```python
# When agents respond, their messages include both reasoning and response
ai_message.content = [
    {
        "type": "reasoning",
        "reasoning": "User wants to translate Japanese text in an image to English. This requires OCR to extract the text, translation from Japanese to English, and then image editing to replace the original text..."
    },
    {
        "type": "text", 
        "text": "I'll help you translate the Japanese text in your image to English..."
    }
]
```

### Accessing Reasoning

```python
from src.logging_utils import extract_text_from_content_blocks

# Extract just the user-facing text
response_text = extract_text_from_content_blocks(ai_message.content)

# Or access reasoning blocks directly
for block in ai_message.content:
    if block.get("type") == "reasoning":
        print(f"AI Reasoning: {block['reasoning']}")

# Note: Chain-of-thought is NOT in response_metadata anymore
# It's now properly structured as ReasoningContentBlock in content
# ai_message.response_metadata  # No longer contains 'cot' field
```

## Benefits of Multimodal Approach

1. **Native LangChain Integration**: Works seamlessly with LangChain's message system
2. **Cleaner Architecture**: No separate file management layer needed
3. **Better Context**: Files and text are part of the same message context
4. **Standardized Format**: Uses LangChain's established content block system
5. **Provider Compatibility**: Works across different LLM providers that support multimodal input
6. **Transparent Reasoning**: AI chain-of-thought is preserved in standard ReasoningContentBlock format

## Migration from Previous API

### From FileInfo System + Old Parameters
```python
# Before (FileInfo + old parameters)
file_info = FileInfo(path="image.png", name="image.png", ...)
result = orchestrator.run(
    user_input="Translate this image",
    files=[file_info]
)

# After (Multimodal + simplified API)
content_blocks = create_content_blocks("image.png", "Translate this image")
message = HumanMessage(content=content_blocks)
result = orchestrator.run(messages=[message])
```

### From Old Text API
```python
# Before (user_input + message_history)
result = orchestrator.run(
    user_input="Hello",
    message_history=previous_messages
)

# After (unified messages parameter)
messages = orchestrator.build_messages(
    user_input="Hello", 
    message_history=previous_messages
)
result = orchestrator.run(messages=messages)

# Or build messages manually
messages = previous_messages + [HumanMessage(content="Hello")]
result = orchestrator.run(messages=messages)
```

## Best Practices

1. **Combine Related Content**: Put related text and files in the same message
2. **Use Appropriate Block Types**: Choose the right content block type for your file
3. **Manage File Sizes**: Large files increase message size and processing time
4. **Provide Context**: Include descriptive text with your files
5. **Handle Errors**: Check file existence and handle encoding errors gracefully

## Integration with Path Tools

The multimodal system integrates seamlessly with Genesis's path tools:

- **OCR tools** automatically extract text from image content blocks
- **Translation tools** process text from any content block type
- **Audio tools** handle audio content blocks for transcription
- **Document tools** process file content blocks for PDFs

The orchestrator automatically determines the appropriate tool chain based on content block types and user requests.
