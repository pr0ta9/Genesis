# from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
import os

def setup_llm(type: str, model_name: str, temperature: float = 0.6):
    # if type == "gemini":
    #     return ChatGoogleGenerativeAI(
    #         model=model_name,
    #         google_api_key=os.getenv("GOOGLE_API_KEY"),
    #         temperature=temperature,
    #         timeout=None,
    #         max_retries=2,
    #     )
    if type == "ollama":
        return ChatOllama(
            model=model_name,
            temperature=temperature,
            num_ctx=16384,
            reasoning=True,
            repeat_penalty=1.5,
            
        )
    else:
        raise ValueError(f"Model {type} not supported")

