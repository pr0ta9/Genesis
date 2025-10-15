# from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_aws import ChatBedrockConverse
import os

def setup_llm(
    type: str,
    model_name: str,
    temperature: float = 0.6,
    aws_region: str = None,
    aws_access_key_id: str = None,
    aws_secret_access_key: str = None,
):
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
    elif type == "bedrock":
        if not aws_region or not aws_access_key_id or not aws_secret_access_key:
            raise ValueError("AWS credentials not provided. Please provide aws_region, aws_access_key_id, and aws_secret_access_key parameters.")
        
        return ChatBedrockConverse(
            model=model_name,
            temperature=temperature,
            max_tokens=None,
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
    else:
        raise ValueError(f"Model {type} not supported")

