@echo off
REM Genesis Model Setup Script - Windows
REM Run this after docker-compose up to set up required models

echo 🤖 Setting up Genesis AI models...

REM Wait for Ollama service to be ready
echo ⏳ Waiting for Ollama service...
:wait_loop
docker exec genesis-ollama ollama list >nul 2>&1
if errorlevel 1 (
    echo    Ollama not ready yet, waiting 5 seconds...
    timeout /t 5 /nobreak >nul
    goto wait_loop
)

echo ✅ Ollama service is ready!

REM Pull required models
echo 📥 Pulling gpt-oss:20b model (this may take a while - ~20GB)...
docker exec genesis-ollama ollama pull gpt-oss:20b

echo 🔧 Testing model...
docker exec genesis-ollama ollama run gpt-oss:20b "Hello, this is a test. Respond briefly."

echo ✅ Model setup complete!
echo.
echo 📋 Available models:
docker exec genesis-ollama ollama list

echo.
echo 🚀 Your Genesis application is ready!
echo    Frontend: http://localhost:3000
echo    Backend:  http://localhost:8000
echo    Ollama:   http://localhost:11434
