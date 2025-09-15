"""
Precedent search and storage using TiDB vector search capabilities.
Handles embedding generation and semantic search for workflow precedents.
"""
import json
import os
import re
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

# Import TiDB vector client and reranker
from pytidb import TiDBClient
from pytidb.rerankers import Reranker
from sentence_transformers import SentenceTransformer

# Remove this - now initialized in initialize_global_clients()

# Global instances - initialized once during startup
_tidb_client = None
_reranker = None
_embedding_model = None

# Initialize components once during startup (called from main.py)
def initialize_global_clients():
    """Initialize global TiDB client, reranker, and embedding model once during startup."""
    global _tidb_client, _reranker, _embedding_model
    
    print("🔧 [PRECEDENT] Initializing global precedent clients...")
    
    if _tidb_client is None:
        connection_string = os.environ.get('TIDB_CONNECTION_STRING')
        if not connection_string:
            raise ValueError("TIDB_CONNECTION_STRING environment variable not set")
        _tidb_client = TiDBClient.connect(connection_string)
        print("✅ [PRECEDENT] TiDB client initialized successfully")
    
    if _reranker is None:
        print("🔧 [PRECEDENT] Loading reranker model: jina_ai/jina-reranker-v1-tiny-en...")
        _reranker = Reranker(model_name="jina_ai/jina-reranker-v1-tiny-en")
        print("✅ [PRECEDENT] Reranker initialized successfully")
    
    if _embedding_model is None:
        print("🔧 [PRECEDENT] Loading embedding model: all-MiniLM-L6-v2...")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        # Test embedding dimensions
        test_embedding = _embedding_model.encode("test")
        dimensions = len(test_embedding)
        print(f"✅ [PRECEDENT] Embedding model initialized successfully")
        print(f"🧠 [PRECEDENT] Model produces {dimensions}-dimensional embeddings")
        
        if dimensions != 384:
            print(f"⚠️  [PRECEDENT] WARNING: Expected 384 dimensions but got {dimensions}")
            print(f"  Make sure your TiDB table uses VECTOR({dimensions}) column")
    
    print("🎉 [PRECEDENT] All global clients initialized successfully!")


def _get_tidb_client():
    """Get the global TiDB client (must be initialized first via initialize_global_clients())."""
    if _tidb_client is None:
        raise RuntimeError("TiDB client not initialized. Call initialize_global_clients() first.")
    return _tidb_client


def _get_precedent_table():
    """Get the precedent table from TiDB client."""
    print("📋 [PRECEDENT] Getting TiDB precedent table...")
    client = _get_tidb_client()
    
    # Ensure we're using the correct database
    try:
        current_db = client.current_database()
        print(f"📊 [PRECEDENT] Current database: {current_db}")
        
        if current_db != "precedent_db":
            print(f"🔄 [PRECEDENT] Switching to precedent_db database...")
            client.use_database("precedent_db")
            print(f"✅ [PRECEDENT] Now using database: {client.current_database()}")
        
        # List available tables for debugging
        tables = client.list_tables()
        print(f"📋 [PRECEDENT] Available tables: {tables}")
        
        # Attempt to open the precedent table
        table = client.open_table("precedent")
        
        if table is None:
            error_msg = (
                "❌ [PRECEDENT] Table 'precedent' exists but cannot be opened. "
                "This usually means the table wasn't created with vector search capabilities. "
                "Please recreate the table with proper VECTOR column and indexing."
            )
            print(error_msg)
            raise RuntimeError(error_msg)
        
        print(f"✅ [PRECEDENT] TiDB precedent table opened successfully")
        return table
        
    except Exception as e:
        print(f"❌ [PRECEDENT] Failed to get precedent table: {e}")
        print("Please ensure:")
        print("  1. The 'precedent_db' database exists")
        print("  2. The 'precedent' table exists with vector search capabilities")
        print("  3. The table has a VECTOR(384) column for embeddings (all-MiniLM-L6-v2 dimensions)")
        print("  4. The table has a vector index created with: CREATE VECTOR INDEX idx_embedding ON precedent ((VEC_COSINE_DISTANCE(embedding))) USING HNSW;")
        raise


def generate_embedding(text: str) -> List[float]:
    """
    Generate vector embedding for the given text.
    
    Args:
        text: Text to embed
        
    Returns:
        List of floats representing the vector embedding
    """
    if _embedding_model is None:
        raise RuntimeError("Embedding model not initialized. Call initialize_global_clients() first.")
    embedding = _embedding_model.encode(text)
    return embedding.tolist()


def create_description_for_embedding(objective: str,
                                   chosen_path: List[Dict[str, Any]],
                                   messages: str) -> str:
    """
    Create a comprehensive description for vector embedding in the format:
    Objective: [objective]
    Workflow: [tool1_short_desc -> tool2_short_desc -> tool3_short_desc]  
    conversation: [messages]
    
    Args:
        objective: The task objective
        chosen_path: List of workflow path steps with metadata
        messages: Conversation messages (already formatted as string)
        
    Returns:
        Formatted description string optimized for search
    """
    # Build workflow description from chosen path
    if chosen_path and len(chosen_path) > 0:
        workflow_steps = []
        for step in chosen_path:
            # Get the description, but only take the part before the first line break
            full_desc = step.get('description', step.get('name', 'Unknown step'))
            # Split by \n and take only the first line (the concise description)
            short_desc = full_desc.split('\n')[0].strip()
            workflow_steps.append(short_desc)
        workflow_desc = " -> ".join(workflow_steps)
    else:
        workflow_desc = "No workflow path available"
    
    # Clean messages by removing file attachments for better vector matching
    cleaned_messages = _clean_messages_for_embedding(messages)
    
    # Format according to your specification  
    description = f"""Objective: {objective}
Workflow: {workflow_desc}
conversation: {cleaned_messages[:500]}"""  # Limit message length to avoid embedding size issues
    
    return description


def _clean_messages_for_embedding(messages: str) -> str:
    """
    Remove file attachments from messages for cleaner vector matching.
    
    Pattern from websocket.py:
    orchestrator_content = f"{content}\n\n<files>\n{files_text}\n</files>"
    """
    
    # Remove XML-style file attachments: <files>...</files>
    cleaned = re.sub(r'\n\n<files>.*?</files>', '', messages, flags=re.DOTALL)
    
    # Also clean up any standalone file reference patterns that might exist
    # Remove lines that look like file paths or references
    cleaned = re.sub(r'^.*\.(txt|md|py|js|ts|json|xml|html|css|sql|yaml|yml|csv|pdf).*$', '', cleaned, flags=re.MULTILINE)
    
    # Remove excessive whitespace
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    cleaned = cleaned.strip()
    
    return cleaned


def search_similar_precedents(query_text: str,
                             threshold: float = 0.7,
                             limit: int = 3) -> List[Dict[str, Any]]:
    """
    Search for similar precedents using TiDB hybrid search (vector + full-text).
    Uses the TiDB SDK for simple hybrid search with reranking.
    
    Args:
        query_text: Text to search for similar precedents
        threshold: Cosine similarity threshold (0.0 to 1.0, higher=more similar)
        limit: Maximum number of results
        
    Returns:
        List of precedent dictionaries with cosine similarity scores.
        Each dict contains a 'score' field with values 0.0-1.0 where:
        - 1.0 = Perfect match
        - 0.8+ = High similarity (recommended for precedent matching)
        - 0.0 = No similarity
        
    Note: Converts TiDB distance (lower=better) to cosine similarity (higher=better)
    for intuitive interpretation in orchestrator logic.
    """
    print(f"🔍 [PRECEDENT SEARCH] Starting search for: '{query_text[:100]}...'")
    print(f"📊 [PRECEDENT SEARCH] Parameters: threshold={threshold}, limit={limit}")
    
    try:
        table = _get_precedent_table()
        
        # Hybrid search with reranking - exactly like the documentation
        if _reranker is None:
            raise RuntimeError("Reranker not initialized. Call initialize_global_clients() first.")
        
        print("🔍 [PRECEDENT SEARCH] Executing TiDB hybrid search with reranking...")
        results = (
            table.search(query_text, search_type="hybrid")
            .rerank(_reranker, "description")  # Rerank based on description field
            .limit(limit)
            .to_dict()  # Convert to dictionary format
        )
        print(f"📋 [PRECEDENT SEARCH] TiDB returned {len(results)} raw results")
        
        # Convert results to our expected format
        print("🔄 [PRECEDENT SEARCH] Converting TiDB results to precedent format...")
        precedents = []
        for i, result in enumerate(results):
            # Convert TiDB distance to cosine similarity for intuitive scoring
            distance = result.get("distance", 1.0)
            similarity_score = max(0.0, 1.0 - distance)  # Ensure non-negative
            print(f"📊 [PRECEDENT SEARCH] Result {i+1}: distance={distance:.4f}, similarity={similarity_score:.4f}")
            
            # Extract metadata and document fields
            precedent_dict = {
                "id": result.get("id"),
                "description": result.get("description", result.get("document", "")),
                "path": json.loads(result["path"]) if isinstance(result.get("path"), str) else result.get("path"),
                "router_format": json.loads(result["router_format"]) if isinstance(result.get("router_format"), str) else result.get("router_format"),
                "messages": result.get("messages", ""),
                "objective": result.get("objective", ""),
                "is_complex": result.get("is_complex", False),
                "input_type": result.get("input_type", ""),
                "type_savepoint": json.loads(result["type_savepoint"]) if isinstance(result.get("type_savepoint"), str) else result.get("type_savepoint", []),
                "created_at": result.get("created_at"),
                "score": similarity_score  # Universal cosine similarity score (0.0-1.0, higher=better)
            }
            
            # Only include results above threshold (now using similarity)
            if precedent_dict["score"] >= threshold:
                precedents.append(precedent_dict)
                print(f"✅ [PRECEDENT SEARCH] Added precedent {i+1}: ID={precedent_dict['id']}, score={precedent_dict['score']:.4f}")
                print(f"🎯 [PRECEDENT SEARCH] Precedent objective: '{precedent_dict['objective'][:100]}...'")
            else:
                print(f"❌ [PRECEDENT SEARCH] Skipped precedent {i+1}: score={precedent_dict['score']:.4f} < threshold={threshold}")
        
        print(f"🎉 [PRECEDENT SEARCH] Search complete! Found {len(precedents)} precedents above threshold")
        return precedents
        
    except Exception as e:
        print(f"❌ [PRECEDENT SEARCH] Error in TiDB hybrid search: {e}")
        print(f"🔧 [PRECEDENT SEARCH] Returning empty results due to error")
        return []


def save_workflow_precedent(objective: str,
                           chosen_path: List[Dict[str, Any]],
                           router_format: Dict[str, Any],
                           messages: str,
                           input_type: str,
                           is_complex: bool,
                           type_savepoint: List[str]) -> Optional[str]:
    """
    Save a new precedent with vector embedding using TiDB SDK.
    Uses the structured format from create_description_for_embedding.
    
    Args:
        objective: Task objective
        chosen_path: Workflow path as list of tool metadata
        router_format: Router response format
        messages: Conversation messages string
        input_type: Type of input 
        is_complex: Whether task is complex
        type_savepoint: List of type savepoints
        
    Returns:
        ID of created precedent, or None if failed
    """
    print(f"💾 [PRECEDENT SAVE] Starting precedent save process...")
    print(f"🎯 [PRECEDENT SAVE] Objective: '{objective[:100]}...'")
    print(f"📊 [PRECEDENT SAVE] Workflow has {len(chosen_path)} steps, input_type: {input_type}, complex: {is_complex}")
    
    try:
        table = _get_precedent_table()
        
        # Create formatted description for embedding and search
        print("📝 [PRECEDENT SAVE] Creating formatted description for embedding...")
        description = create_description_for_embedding(
            objective=objective,
            chosen_path=chosen_path,
            messages=messages
        )
        print(f"📝 [PRECEDENT SAVE] Description preview: '{description[:200]}...'")
        
        # Generate embedding from the formatted description
        print("🧠 [PRECEDENT SAVE] Generating vector embedding...")
        embedding = generate_embedding(description)
        print(f"🧠 [PRECEDENT SAVE] Generated embedding with {len(embedding)} dimensions")
        
        # Generate unique ID for this precedent
        import uuid
        precedent_id = str(uuid.uuid4())
        print(f"🆔 [PRECEDENT SAVE] Generated precedent ID: {precedent_id}")
        
        # Prepare document for insertion - exactly like the documentation
        document = {
            "id": precedent_id,
            "text": description,  # The formatted description for search
            "embedding": embedding,
            "metadata": {
                "objective": objective,
                "path": chosen_path,  # Store full path metadata
                "router_format": router_format,
                "messages": messages,
                "input_type": input_type,
                "is_complex": is_complex,
                "type_savepoint": type_savepoint,
                "created_at": datetime.utcnow().isoformat()
            }
        }
        
        # Insert using TiDB SDK - like the documentation
        print("🔄 [PRECEDENT SAVE] Inserting document into TiDB...")
        table.insert(
            ids=[document["id"]],
            texts=[document["text"]],
            embeddings=[document["embedding"]], 
            metadatas=[document["metadata"]]
        )
        
        print(f"✅ [PRECEDENT SAVE] Successfully saved precedent with ID: {precedent_id}")
        print(f"📊 [PRECEDENT SAVE] Document size: text={len(document['text'])} chars, metadata keys={list(document['metadata'].keys())}")
        return precedent_id
        
    except Exception as e:
        print(f"❌ [PRECEDENT SAVE] Error saving precedent: {e}")
        print(f"🔧 [PRECEDENT SAVE] Failed to save precedent for objective: '{objective[:100]}...'")
        return None
