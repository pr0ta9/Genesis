# Genesis AI Assistant

A sophisticated multimodal AI assistant with LangGraph orchestration, supporting images, audio, documents, and video processing using OpenAI's gpt-oss models.

## What Genesis Can Do

- **AI-Powered Image Processing**: Intelligent image manipulation, OCR, text removal, and inpainting
- **Audio Processing**: Advanced noise suppression and audio enhancement
- **Document Processing**: OCR, translation, and text extraction from images and PDFs
- **Web Search**: Integrated web search capabilities
- **Real-time Processing**: WebSocket support for live updates and streaming
- **Full-Stack Architecture**: Python backend with FastAPI, Next.js frontend with React and TypeScript

## Quick Start Guide

### Step 1: Install Prerequisites

#### Required Software
1. **[Ollama](https://ollama.com/download)** - Download and install for your operating system
2. **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** - Install Docker and Docker Compose
3. **[Git](https://git-scm.com/downloads)** - For cloning the repository

#### Optional (for local development)
- Python 3.12+
- Node.js 20+

### Step 2: Clone and Setup Project

```bash
# Clone the repository
git clone <your-repository-url>
cd Genesis

# Make sure Docker is running
docker --version
docker-compose --version
```

### Step 3: Download AI Models

Genesis requires OpenAI's gpt-oss models. After installing Ollama:

```bash
# Start Ollama (if not already running)
ollama serve

# In a new terminal, download the AI model
# Option A: Smaller model (14GB, requires 16GB+ RAM) - RECOMMENDED
ollama pull gpt-oss:20b

# Option B: Larger model (65GB, requires 80GB+ memory) - For advanced users
# ollama pull gpt-oss:120b

# Verify the model downloaded successfully
ollama list
```

**Important**: The model download may take 10-30 minutes depending on your internet speed.

### Step 4: Configure Environment

Create your environment files:

#### Create `.env` in project root:
```env
# === Required Configuration ===
GENESIS_KEEP_WORKSPACE=1
GENESIS_DEV_MODE=0

# === Database Configuration (Optional but Recommended) ===
# Sign up at https://tidbcloud.com/ for free tier
# TIDB_HOST=your-cluster.cluster.tidbcloud.com
# TIDB_PORT=4000
# TIDB_USERNAME=your_username  
# TIDB_PASSWORD=your_password
# TIDB_DATABASE=precedent_db

# === Optional API Keys (for enhanced functionality) ===
# GOOGLE_API_KEY=your_google_api_key
# BRAVE_API_KEY=your_brave_search_api_key
# SERPER_API_KEY=your_google_serper_api_key
```

#### Create `frontend/.env.local`:
```env
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

### Step 5: Start Genesis

Choose your deployment mode:

#### Option A: Standard Setup (Recommended)
```bash
# Start all services
docker-compose up -d

# View logs to ensure everything started correctly
docker-compose logs -f

# When everything is running, you should see:
# ✓ Database connected
# ✓ Ollama model loaded
# ✓ Frontend and backend ready
```

#### Option B: GPU Mode (Experimental - Advanced Users Only)
⚠️ **Warning**: GPU mode is experimental and may have compatibility issues.

```bash
# Only use if you have NVIDIA GPU with 12GB+ VRAM
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### Step 6: Access Genesis

Once everything is running:

- **🌟 Genesis App**: http://localhost:3000
- **📚 API Documentation**: http://localhost:8000/docs
- **🔧 Backend API**: http://localhost:8000

### Step 7: Test Your Setup

1. **Upload a Test Image**: Use `tests/examples/test.png`
2. **Try OCR**: Extract text from the image
3. **Test Audio**: Upload `tests/examples/test.wav` and try denoising
4. **Experiment**: Try different combinations of tools

## Available Tools

Genesis provides these AI-powered tools:

### 🖼️ Image Processing
- **OCR**: Extract text from images and PDFs
- **Text Removal**: Intelligently erase text from images
- **Inpainting**: Replace text with custom fonts and styles
- **Translation**: Multi-language text translation

### 🎵 Audio Processing
- **Denoise**: Remove background noise from audio files

### 🌐 Web & Search
- **Web Search**: Search the internet using DuckDuckGo

### 📝 Workflow Examples
- **Document Digitization**: Image → OCR → Translate → Export
- **Image Cleanup**: Image → OCR → Remove Text → Save Clean Image
- **Audio Enhancement**: Audio → Denoise → Download Clean Audio

## Troubleshooting

### Genesis Won't Start

**Problem**: "Cannot connect to Ollama"
```bash
# Check if Ollama is running
ollama list

# If not running, start it
ollama serve

# Verify your model is available
ollama list | grep gpt-oss
```

**Problem**: "Frontend can't connect to backend"
```bash
# Check if backend is running
docker-compose logs backend

# Restart services
docker-compose restart
```

**Problem**: Docker containers keep stopping
```bash
# Check Docker logs
docker-compose logs

# Make sure you have enough RAM (16GB+ recommended)
# Set GENESIS_DEV_MODE=0 in .env to prevent auto-reload issues
```

### Performance Issues

**Slow Processing**: 
- Ensure you're using the 20B model (not 120B) unless you have 80GB+ RAM
- Close other memory-intensive applications
- Consider using CPU mode instead of GPU mode

**First Run Slow**: 
- PaddleOCR models download on first OCR/translation use
- Subsequent runs will be much faster

### Getting Help

1. **Check logs**: `docker-compose logs -f`
2. **Verify setup**: Ensure Ollama is running with `ollama list`
3. **Restart services**: `docker-compose restart`
4. **Clean start**: `docker-compose down && docker-compose up -d`

## Advanced Configuration

### Database Setup (Optional but Recommended)

Genesis can store processing history and learn from your workflows:

1. **Sign up**: Create free account at [TiDB Cloud](https://tidbcloud.com/)
2. **Create cluster**: Set up a new TiDB cluster
3. **Get credentials**: Copy connection details from cluster overview
4. **Update `.env`**: Add your TiDB credentials to enable smart features

### API Keys (Optional)

Enhance Genesis with additional services:

- **Google Gemini**: Alternative AI model for certain tasks
- **Brave Search**: Enhanced web search capabilities  
- **Serper**: Google search integration

Add these to your `.env` file as needed.

### Development Mode

For developers who want to modify Genesis:

```bash
# Enable development mode with hot reload
# Set in .env: GENESIS_DEV_MODE=1

# Or run development compose
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## System Requirements

### Minimum Requirements (Recommended Setup)
- **RAM**: 16GB (for gpt-oss:20b model)
- **Storage**: 20GB free space
- **CPU**: Any modern CPU with AVX2 support
- **OS**: Windows 10+, macOS 10.15+, or modern Linux

### High-Performance Setup
- **RAM**: 32GB+ 
- **Storage**: SSD with 50GB+ free space
- **CPU**: Multi-core processor (8+ cores recommended)

### GPU Requirements (Optional, Experimental)
- **GPU**: NVIDIA RTX 40/50 series with 12GB+ VRAM
- **CUDA**: 12.8+ compatible drivers
- **RAM**: 24GB+ system RAM

## Support & Contributing

### Getting Support
- Check the troubleshooting section above
- Review Docker logs: `docker-compose logs`
- Ensure all prerequisites are properly installed

### Contributing
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Test your changes thoroughly
4. Commit your changes (`git commit -m 'Add amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

## License

This project is licensed under the Apache 2.0 License. The OpenAI gpt-oss models are also licensed under Apache 2.0.

---

## Project Structure (For Developers)

```
Genesis/
├── backend/                # FastAPI backend
│   ├── app/               # Application code  
│   └── requirements-docker.txt
├── frontend/              # Next.js frontend
│   ├── src/              # React components
│   └── Dockerfile
├── src/                  # Core Python modules
│   ├── agents/          # LangGraph agents
│   ├── tools/           # AI tools and utilities
│   └── orchestrator.py  # Main orchestrator
├── tests/
│   └── examples/        # Test files (test.png, test.wav)
├── docker-compose.yml   # Main Docker configuration
├── .env.example        # Environment template
└── README.md
```