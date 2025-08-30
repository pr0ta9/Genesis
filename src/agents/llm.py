from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
import os
from dotenv import load_dotenv


def setup_llm(type: str, model_name: str, temperature: float = 0):
    load_dotenv()
    if type == "gemini":
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=temperature,
            timeout=None,
            max_retries=2,
        )
    elif type == "ollama":
        return ChatOllama(
            model=model_name,
            temperature=temperature,
        )
    else:
        raise ValueError(f"Model {type} not supported")

