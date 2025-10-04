"""
Local Weaviate client with one-time schema ensure for the `precedent` collection.

Usage (at app startup):
    from src.db.client import get_weaviate_client, close_weaviate_client
    client = get_weaviate_client()  # connects locally, ensures collection
    # ... use client throughout the app ...
    close_weaviate_client()  # on shutdown
"""
import os
import weaviate
from weaviate.classes.config import Configure, DataType, Property

def create_precedent_collection(client):
    # Get Ollama endpoint from environment
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    
    return client.collections.create(
        "precedent",
        vector_config=Configure.Vectors.text2vec_ollama(
            name="default",
            source_properties=["description"],
            api_endpoint=ollama_url,
            model="nomic-embed-text"  # Default embedding model
        ),
        # reranker_config=Configure.Reranker.transformers(),  # Disabled: requires external API
        properties=[
            Property(name="uid", data_type=DataType.UUID),
            Property(name="description", data_type=DataType.TEXT, description="Task description + overall workflow description + conversation log (used for semantic search)"),
            # PathToolMetadata list - structured object array
            Property(
                name="path", 
                data_type=DataType.OBJECT_ARRAY,
                description="List of PathToolMetadata objects representing the workflow",
                nested_properties=[
                    Property(name="name", data_type=DataType.TEXT),
                    Property(name="description", data_type=DataType.TEXT),
                    Property(name="input_key", data_type=DataType.TEXT),
                    Property(name="output_key", data_type=DataType.TEXT),
                    Property(name="input_params", data_type=DataType.TEXT_ARRAY),
                    Property(name="output_params", data_type=DataType.TEXT_ARRAY),
                    # Use TEXT for dynamic dict fields (stored as JSON strings)
                    Property(name="param_types", data_type=DataType.TEXT),
                    Property(name="required_inputs", data_type=DataType.TEXT),
                    Property(name="default_params", data_type=DataType.TEXT),
                ]
            ),
            # PathItem list (router format) - structured object array  
            Property(
                name="router_format",
                data_type=DataType.OBJECT_ARRAY,
                description="List of PathItem objects representing the router response",
                nested_properties=[
                    Property(name="path", data_type=DataType.OBJECT_ARRAY, nested_properties=[
                        Property(name="name", data_type=DataType.TEXT),
                        # Use TEXT for dynamic dict field (stored as JSON string)
                        Property(name="param_values", data_type=DataType.TEXT),
                    ]),
                    Property(name="reasoning", data_type=DataType.TEXT),
                    Property(name="clarification_question", data_type=DataType.TEXT),
                ]
            ),
            Property(name="messages", data_type=DataType.TEXT, description="Conversation paragraph of the workflow in text format"),
            Property(name="objective", data_type=DataType.TEXT),
            Property(name="is_complex", data_type=DataType.BOOL),
            Property(name="input_type", data_type=DataType.TEXT),
            # WorkflowTypeEnum list - simple string array
            Property(
                name="type_savepoint", 
                data_type=DataType.TEXT_ARRAY, 
                description="List of WorkflowTypeEnum values as strings"
            ),
            Property(name="created_at", data_type=DataType.DATE),
            Property(name="updated_at", data_type=DataType.DATE),
        ],
    )

def get_weaviate_client() -> weaviate.WeaviateClient:
    """Return a process-wide local Weaviate client and ensure schema exists."""
    global _client
    if _client is not None:
        return _client

    # Get Weaviate URL from environment variable (Docker uses 'weaviate:8080', local uses 'localhost:8080')
    weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    
    # Parse URL to extract host and port
    if "://" in weaviate_url:
        scheme, rest = weaviate_url.split("://", 1)
        if ":" in rest:
            host, port_str = rest.split(":", 1)
            port = int(port_str)
        else:
            host = rest
            port = 443 if scheme == "https" else 8080
    else:
        # Handle URLs without scheme
        if ":" in weaviate_url:
            host, port_str = weaviate_url.split(":", 1)
            port = int(port_str)
        else:
            host = weaviate_url
            port = 8080

    # Use WeaviateClient with URL-based connection
    _client = weaviate.WeaviateClient(
        connection_params=weaviate.connect.ConnectionParams.from_url(
            url=weaviate_url,
            grpc_port=50051
        )
    )
    _client.connect()

    # Readiness check
    if not _client.is_ready():
        _client.close()
        raise RuntimeError(f"Weaviate is not ready at {weaviate_url}. Ensure Weaviate is running and accessible.")

    if not _client.collections.exists("precedent"):
        create_precedent_collection(_client)

    return _client

def close_weaviate_client() -> None:
    """Close the global client (call on application shutdown)."""
    global _client
    if _client is not None:
        try:
            _client.close()
        finally:
            _client = None


__all__ = [
    "get_weaviate_client",
    "close_weaviate_client",
]

_client = None