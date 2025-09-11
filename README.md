# Genesis AI Assistant

A sophisticated multimodal AI assistant with LangGraph orchestration, supporting images, audio, documents, and video processing using OpenAI's gpt-oss models.

## Features

- **AI-Powered Image Processing**: Genesis leverages advanced AI models for intelligent image manipulation
- **Full-Stack Architecture**: Python backend with FastAPI, Next.js frontend with React and TypeScript
- **Docker Support**: Containerized deployment for easy setup and scalability (CPU/GPU modes)
- **Real-time Processing**: WebSocket support for live updates and streaming
- **Local AI Models**: Integration with OpenAI's gpt-oss models via Ollama for powerful reasoning and agentic tasks
- **Multiple Deployment Options**: Host Ollama (recommended) or containerized Ollama

## Prerequisites

### Required
- **[Ollama](https://ollama.com/download)** - Local AI model runtime (required for AI functionality)
- **Docker and Docker Compose** - For containerized deployment
- **Git** - For version control

### For Local Development (Optional)
- Python 3.12+ (backend development)
- Node.js 20+ (frontend development)

## AI Model Setup (Required)

Genesis requires OpenAI's gpt-oss models to function. After installing Ollama, download the required AI model:

```bash
# Download OpenAI's gpt-oss 20B model (14GB, requires 16GB+ RAM)
ollama pull gpt-oss:20b

# OR download the larger 120B model (65GB, requires 80GB+ memory)  
ollama pull gpt-oss:120b

# Verify the model is available
ollama list
```

**Model Information**: [OpenAI's gpt-oss models](https://ollama.com/library/gpt-oss) are designed for powerful reasoning, agentic tasks, and versatile developer use cases. The 20B model (14GB) is optimized for lower latency and can run on systems with as little as 16GB memory.

### Model Features
- **Agentic capabilities**: Function calling, web browsing, Python tool calls, and structured outputs
- **Full chain-of-thought**: Complete access to the model's reasoning process
- **Configurable reasoning effort**: Adjust reasoning effort (low, medium, high) based on your use case
- **Apache 2.0 license**: Build freely without copyleft restrictions

## Environment Configuration

Create the required environment files:

### `.env` (Project Root)
```env
GENESIS_KEEP_WORKSPACE=1
```

### `frontend/.env.local`
```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## Docker Quick Start

### Step 1: Ensure Ollama is Running
Make sure Ollama is installed and the gpt-oss model is downloaded:

```bash
# Check if Ollama is running
ollama list

# If gpt-oss is not listed, download it:
ollama pull gpt-oss:20b
```

### Step 2: Choose Your Deployment Mode

#### CPU Mode (Default - Recommended)
Uses your host system's Ollama for best performance:

```bash
# Start all services (uses host Ollama)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

#### GPU Mode (NVIDIA GPU Acceleration) - ⚠️ EXPERIMENTAL
For systems with CUDA-compatible GPUs, uses official PyTorch CUDA 12.8 image:

⚠️ **Stability Warning**: The GPU version is not fully tested across different environments and uses CUDA 12.8, which may have compatibility issues with some GPU setups. **We recommend using the CPU version for production use.**

```bash
# Start with GPU support (still uses host Ollama)
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# View logs
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml logs -f

# Stop services
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml down
```

**GPU Requirements:**
- NVIDIA GPU with CUDA 12.8+ support
- NVIDIA Docker runtime installed
- 12GB+ GPU memory recommended

#### Development Mode
For development with hot reload:

```bash
# Start in development mode
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Step 3: Access the Application
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## Available Tools & Testing

Genesis comes with a comprehensive set of AI tools for multimodal processing:

### 🛠️ Available Tools

#### Agent Tools
- **`web_search`** - Web search functionality using DuckDuckGo

#### Path Tools (Image & Audio Processing)
- **`denoise`** - Audio noise suppression using acoustic models
- **`erase`** - Intelligent text removal from images using LaMa inpainting
- **`ocr`** - Optical Character Recognition for images and PDFs (PaddleOCR)
- **`inpaint_text`** - Advanced text replacement in images with custom fonts
- **`translate`** - Multi-language text translation

### 🧪 Testing Examples

The project includes sample files for testing functionality:

- **`tests/examples/test.png`** - Sample image for testing OCR, text removal, and inpainting
- **`tests/examples/test.wav`** - Sample audio file for testing audio denoising

**Usage Example:**
1. Upload the test image through the frontend at http://localhost:3000
2. Try OCR to extract text from the image
3. Use the erase tool to remove detected text
4. Upload the test audio to experiment with denoising

### 🎯 Workflow Examples
- **Document Processing**: Upload image → OCR → Translate → Export
- **Image Cleanup**: Upload image → OCR → Erase text → Save clean image
- **Audio Enhancement**: Upload audio → Denoise → Download clean audio

## Deployment Options

### Option 1: Host Ollama (Default - Recommended)
The default configuration uses your system's Ollama installation:

✅ **Benefits:**
- Better performance (no Docker overhead)
- Uses existing Ollama models and configuration  
- Simpler resource management
- Faster startup times

✅ **Requirements:**
- Ollama installed and running on host
- gpt-oss model downloaded (`ollama pull gpt-oss:20b`)

### Option 2: Docker Ollama (Alternative)
If you prefer a fully containerized setup, you can uncomment the Ollama service in `docker-compose.yml` and change the backend environment variables:

```yaml
# In docker-compose.yml, uncomment the ollama service section
# Change backend environment to:
- OLLAMA_BASE_URL=http://ollama:11434  
- OLLAMA_HOST=ollama:11434
```

Then run the setup script to download models into the container:
```bash
# Windows
setup-models.bat

# Linux/macOS  
chmod +x setup-models.sh && ./setup-models.sh
```

## Troubleshooting

### Common Issues

**"Cannot connect to Ollama"**
- Ensure Ollama is running: `ollama list`
- Check if gpt-oss model is available: `ollama pull gpt-oss:20b`
- Verify Ollama is accessible on port 11434

**Frontend cannot connect to backend**
- Frontend connects to `localhost:8000` (not `backend:8000`)
- Ensure Docker port mapping is correct (8000:8000)

**GPU mode not working**
- Ensure NVIDIA Docker runtime is installed
- Verify CUDA compatibility with your GPU
- Check Docker GPU access: `docker run --rm --gpus all nvidia/cuda:12.0-runtime-ubuntu22.04 nvidia-smi`

## System Requirements

### Minimum (CPU Mode - Recommended)
- 16GB RAM (for gpt-oss:20b model)
- 20GB free disk space
- CPU with AVX2 support
- Ollama installed with gpt-oss:20b model

### GPU Mode (Experimental - Not Recommended for Production)
- 24GB+ RAM
- NVIDIA RTX 40/50 series GPU with 12GB+ VRAM
- CUDA 12.8+ compatible drivers (compatibility issues possible)
- Docker with NVIDIA container runtime

### Enterprise (120B model)
- 80GB+ RAM or GPU memory
- High-end workstation or server setup
- Ollama with gpt-oss:120b model

## Project Structure

```
Genesis/
├── backend/                 # FastAPI backend
│   ├── app/                # Application code
│   └── requirements-docker.txt
├── frontend/               # Next.js frontend
│   ├── src/               # React components
│   └── Dockerfile
├── src/                   # Core Python modules
│   ├── agents/           # LangGraph agents
│   ├── tools/            # AI tools and utilities
│   └── orchestrator.py   # Main orchestrator
├── docker-compose.yml    # Main Docker configuration
├── docker-compose.gpu.yml # GPU overrides
├── Dockerfile            # Backend CPU image
├── Dockerfile.gpu-cuda12 # Backend GPU image
└── README.md
```

## Development

### Local Development Setup

1. **Backend Development**:
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# or: source venv/bin/activate  # Linux/macOS

pip install -r requirements-docker.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

2. **Frontend Development**:
```bash
cd frontend
npm install
npm run dev
```

### Building Custom Images

```bash
# Build CPU version
docker build -t genesis-backend:cpu .

# Build GPU version  
docker build -f Dockerfile.gpu-cuda12 -t genesis-backend:gpu .

# Build frontend
docker build -t genesis-frontend ./frontend
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

The OpenAI gpt-oss models are licensed under the Apache 2.0 license.

## Acknowledgments

- [OpenAI](https://openai.com) for the gpt-oss models
- [Ollama](https://ollama.com) for local AI model runtime
- [LangChain](https://langchain.com) for AI orchestration framework
- [FastAPI](https://fastapi.tiangolo.com) for the backend framework
- [Next.js](https://nextjs.org) for the frontend framework