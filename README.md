# Genesis AI Assistant

A sophisticated multimodal AI assistant with LangGraph orchestration, supporting images, audio, documents, and video processing — powered by **NVIDIA Nemotron 3 Super 120B** running locally on **DGX Spark (GB10)**.

Built for [Hack for Impact @ GTC 2026](https://luma.com/gtc-hack-for-impact) | Environmental Impact Track

## Environmental Impact

Genesis enables environmental analysis through its multimodal AI pipeline:
- **Image Analysis** — Process environmental photos: landscape documentation, pollution monitoring, species identification from field images, trail sign OCR
- **Document Processing** — Extract data from environmental reports, research papers, and field notes via OCR and translation
- **Audio Processing** — Denoise field recordings for wildlife monitoring and acoustic ecology research
- **Web Research** — Pull real-time environmental data, air quality reports, and conservation news
- All AI inference runs **100% locally** on DGX Spark — zero cloud compute, minimal carbon footprint

## Features

- **AI-Powered Multimodal Processing**: Images, audio, documents, and video through intelligent tool chaining
- **Full-Stack Architecture**: Python backend with FastAPI, Next.js frontend with React and TypeScript
- **Docker Support**: Containerized deployment for easy setup and scalability (CPU/GPU/DGX Spark modes)
- **Real-time Processing**: WebSocket support for live updates and streaming
- **Local AI Models**: Nemotron 3 Super 120B via Ollama on NVIDIA DGX Spark for powerful reasoning and agentic tasks
- **Multiple Deployment Options**: Host Ollama (recommended), containerized Ollama, or DGX Spark native

## Prerequisites

### Required
- **[Ollama](https://ollama.com/download)** - Local AI model runtime (required for AI functionality)
- **Docker and Docker Compose** - For containerized deployment
- **Git** - For version control

### For Local Development (Optional)
- Python 3.12+ (backend development)
- Node.js 20+ (frontend development)

## AI Model Setup (Required)

Genesis uses **NVIDIA Nemotron 3 Super 120B** for optimal performance on DGX Spark, or OpenAI's gpt-oss models as alternatives.

```bash
# Recommended: Nemotron 3 Super 120B on DGX Spark (86GB, requires 128GB unified memory)
ollama pull nemotron-3-super:120b

# Alternative: gpt-oss 20B for smaller systems (14GB, requires 16GB+ RAM)
ollama pull gpt-oss:20b

# Verify the model is available
ollama list
```

Set the model via environment variable:
```bash
export GENESIS_MODEL=nemotron-3-super:120b  # or gpt-oss:20b
```

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

#### DGX Spark Mode (NVIDIA GB10 — Recommended for Hack for Impact)
For NVIDIA DGX Spark with Nemotron 3 Super 120B:

```bash
# Ensure Ollama is running with Nemotron 3 Super
ollama pull nemotron-3-super:120b

# Start with DGX Spark support (uses host Ollama)
docker-compose -f docker-compose.dgx-spark.yml up -d

# View logs
docker-compose -f docker-compose.dgx-spark.yml logs -f
```

**DGX Spark Requirements:**
- NVIDIA DGX Spark (GB10) with 128GB unified memory
- DGX OS (Ubuntu 24.04)
- Ollama with Nemotron 3 Super 120B loaded
- Docker with NVIDIA Container Toolkit

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

**Process didn't run correctly**
- Check backend logs for details. For image OCR/translation tasks, also review stderr/stdout logs inside `backend/outputs/...` (example: `backend/outputs/conv_20250910_211003_6e797bb2/11/01_image_ocr_stderr.log` and `backend/outputs/conv_20250910_211003_6e797bb2/11/01_image_ocr_stdout.log`).

**Image translation first run (PaddleOCR models)**
- The first run may take time while PaddleOCR models are downloaded and cached locally.
- If the backend shows a 403 error during model download, your machine may be unable to reach the Paddle model host. See the PaddleOCR repository for details and guidance: [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR).
- After models download successfully once, they are stored locally and future runs should not encounter this issue.

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

# For running in dev mode
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d frontend

# For running in prod mode
docker-compose up -d

# For shutting down docker
docker compose down
```

## NVIDIA Ecosystem Usage

- **Nemotron 3 Super 120B** — Main agent brain for multimodal task orchestration, reasoning, and environmental analysis
- **NVIDIA DGX Spark (GB10)** — 128GB unified memory enables running 120B parameter model locally
- **Ollama on DGX Spark** — Local model serving with GPU acceleration
- **CUDA 13.0 / sm_121** — Native Blackwell GPU support via custom Dockerfile
- **NVIDIA Container Toolkit** — GPU-accelerated Docker containers

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for details.

The OpenAI gpt-oss models are licensed under the Apache 2.0 license.

## Acknowledgments

- [NVIDIA](https://nvidia.com) for Nemotron 3 Super, DGX Spark, and OpenShell
- [Ollama](https://ollama.com) for local AI model runtime
- [LangChain](https://langchain.com) for AI orchestration framework
- [FastAPI](https://fastapi.tiangolo.com) for the backend framework
- [Next.js](https://nextjs.org) for the frontend framework
