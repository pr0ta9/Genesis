"""
Precedent search and storage using TiDB with MySQLdb.
Handles embedding generation and semantic search for workflow precedents.
"""
import json
import os
import re
import uuid
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager

# MySQLdb imports
import MySQLdb
import MySQLdb.cursors

# Keep the reranker and embedding models as they are
from pytidb.rerankers import Reranker
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv(override=True)

# Global instances - initialized once during startup
_reranker = None
_embedding_model = None
project_root = Path(__file__).parent.parent.parent.parent

def get_mysqlclient_connection(autocommit: bool = True) -> MySQLdb.Connection:
    """Create a mysqlclient connection to TiDB."""
    # Get connection parameters from environment variables
    tidb_host = os.environ.get('TIDB_HOST')
    tidb_port = os.environ.get('TIDB_PORT', 4000)
    tidb_user = os.environ.get('TIDB_USERNAME')
    tidb_password = os.environ.get('TIDB_PASSWORD')
    tidb_db_name = os.environ.get('TIDB_DATABASE', 'precedent_db')
    # ca_path = os.environ.get('CA')
    
    if not all([tidb_host, tidb_user, tidb_password]):
        raise ValueError(
            "Missing required environment variables. Please set:\n"
            "TIDB_HOST, TIDB_USERNAME, TIDB_PASSWORD, TIDB_DATABASE"
        )
    
    # Build connection configuration for TiDB Cloud
    db_conf = {
        "host": tidb_host,
        "port": int(tidb_port),
        "user": tidb_user,
        "password": tidb_password,
        "database": tidb_db_name,
        "autocommit": autocommit,
        "charset": "utf8mb4"
    }
    
    # Add SSL CA path if provided (for windows only)
    # if ca_path:
    #     db_conf["ssl_ca"] = ca_path
    
    return MySQLdb.connect(**db_conf)

@contextmanager
def get_db_connection(autocommit: bool = True):
    """Context manager for database connections."""
    conn = None
    try:
        conn = get_mysqlclient_connection(autocommit=autocommit)
        yield conn
    except Exception as e:
        if conn and not autocommit:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

def validate_table_structure() -> bool:
    """Check if the precedent table has the correct structure."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(MySQLdb.cursors.DictCursor) as cur:
                cur.execute("DESCRIBE precedent")
                columns = cur.fetchall()
                
                # Check for required columns and their types
                column_map = {col['Field']: col for col in columns}
                
                # Required structure validation
                required_checks = [
                    ('id', lambda col: col['Type'].startswith('int') and col['Extra'] == 'auto_increment'),
                    ('description', lambda col: col['Type'] == 'text' and col['Null'] == 'NO'),
                    ('path', lambda col: col['Type'] == 'json' and col['Null'] == 'NO'),
                    ('router_format', lambda col: col['Type'] == 'json' and col['Null'] == 'NO'),
                    ('messages', lambda col: col['Type'] == 'text' and col['Null'] == 'NO'),
                    ('objective', lambda col: col['Type'] == 'text' and col['Null'] == 'NO'),
                    ('is_complex', lambda col: col['Type'] == 'tinyint(1)' and col['Null'] == 'NO'),
                    ('input_type', lambda col: col['Type'] == 'varchar(100)' and col['Null'] == 'NO'),
                    ('type_savepoint', lambda col: col['Type'] == 'json' and col['Null'] == 'NO'),
                    ('embedding', lambda col: col['Type'].startswith('vector') and col['Null'] == 'NO'),
                ]
                
                for field_name, check_func in required_checks:
                    if field_name not in column_map:
                        print(f"❌ [PRECEDENT] Missing required column: {field_name}")
                        return False
                    if not check_func(column_map[field_name]):
                        print(f"❌ [PRECEDENT] Column {field_name} has incorrect type: {column_map[field_name]['Type']}")
                        return False
                
                print("✅ [PRECEDENT] Table structure validation passed")
                return True
                
    except MySQLdb.Error as e:
        if e.args[0] == 1146:  # Table doesn't exist
            print("📋 [PRECEDENT] Table doesn't exist yet")
            return False
        print(f"❌ [PRECEDENT] Error validating table structure: {e}")
        return False

def create_precedent_table():
    """Create the precedent table with correct TiDB VECTOR structure."""
    create_table_sql = """
    CREATE TABLE precedent (
        id INT AUTO_INCREMENT PRIMARY KEY,
        description TEXT NOT NULL COMMENT 'Task description + overall workflow description + conversation log (used for semantic search)',
        path JSON NOT NULL COMMENT 'List of PathToolMetadata in JSON format representing the workflow',
        router_format JSON NOT NULL COMMENT 'Router response in JSON format of the workflow',
        messages TEXT NOT NULL COMMENT 'Conversation paragraph of the workflow in string format',
        objective TEXT NOT NULL COMMENT 'State variable',
        is_complex BOOLEAN NOT NULL COMMENT 'State variable indicating complexity',
        input_type VARCHAR(100) NOT NULL COMMENT 'State variable for input type',
        type_savepoint JSON NOT NULL COMMENT 'State variable as list of strings stored in JSON format',
        embedding VECTOR(384) NOT NULL COMMENT 'Vector embedding of the description for semantic search',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(create_table_sql)
            # Reset AUTO_INCREMENT to start from 1
            cur.execute("ALTER TABLE precedent AUTO_INCREMENT = 1")
            print("✅ [PRECEDENT] Precedent table created successfully")
            print("🔢 [PRECEDENT] AUTO_INCREMENT reset to start from 1")

def ensure_correct_table_structure():
    """Ensure the precedent table has the correct structure, recreating if necessary."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Check if table exists
                cur.execute("SHOW TABLES LIKE 'precedent'")
                table_exists = cur.fetchone() is not None
                
                if table_exists:
                    print("📋 [PRECEDENT] Table exists, validating structure...")
                    if validate_table_structure():
                        print("✅ [PRECEDENT] Table structure is correct")
                        return
                    else:
                        print("⚠️ [PRECEDENT] Table structure is incorrect, dropping and recreating...")
                        cur.execute("DROP TABLE precedent")
                        print("🗑️ [PRECEDENT] Old table dropped")
                
                print("🔧 [PRECEDENT] Creating precedent table with correct structure...")
                create_precedent_table()
                
    except Exception as e:
        print(f"❌ [PRECEDENT] Error ensuring table structure: {e}")
        raise

# Initialize components once during startup (called from main.py)
def initialize_global_clients():
    """Initialize global database connection, reranker, and embedding model once during startup."""
    global _reranker, _embedding_model
    
    print("🔧 [PRECEDENT] Initializing global precedent clients...")
    
    # Test the database connection and ensure correct table structure
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DATABASE() as current_db")
                current_db = cur.fetchone()[0]
                print(f"✅ [PRECEDENT] Connected to TiDB database: {current_db}")
                
                # Ensure the table has the correct structure
                ensure_correct_table_structure()
                    
    except Exception as e:
        print(f"❌ [PRECEDENT] Database connection failed: {e}")
        raise
    
    # Initialize reranker (required)
    if _reranker is None:
        print("🔧 [PRECEDENT] Loading reranker model: jina_ai/jina-reranker-v1-tiny-en...")
        _reranker = Reranker(model_name="jina_ai/jina-reranker-v1-tiny-en")
        print("✅ [PRECEDENT] Reranker initialized successfully")
    
    # Initialize embedding model (required)
    if _embedding_model is None:
        print("🔧 [PRECEDENT] Loading embedding model: all-MiniLM-L6-v2...")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        # Test embedding dimensions
        test_embedding = _embedding_model.encode("test")
        dimensions = len(test_embedding)
        print(f"✅ [PRECEDENT] Embedding model initialized successfully")
        print(f"🧠 [PRECEDENT] Model produces {dimensions}-dimensional embeddings")
        
        if dimensions != 384:
            raise RuntimeError(f"Expected 384 dimensions but got {dimensions}")
    
    print("🎉 [PRECEDENT] Global clients initialization complete!")

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
    
    Patterns to handle:
    1. <files>...</files> blocks (remove entirely)
    2. <file>...</file> individual references (replace with "file_path")
    """
    
    # Remove XML-style file attachment blocks: <files>...</files>
    cleaned = re.sub(r'\n\n<files>.*?</files>', '', messages, flags=re.DOTALL)
    
    # Replace individual file references with generic "file_path"
    # Pattern: <file>/path/to/file.ext</file> -> file_path
    cleaned = re.sub(r'<file>.*?</file>', 'file_path', cleaned, flags=re.DOTALL)
    
    # Also clean up any remaining standalone file reference patterns
    # Remove lines that look like raw file paths or references
    cleaned = re.sub(r'^.*\.(txt|md|py|js|ts|json|xml|html|css|sql|yaml|yml|csv|pdf|wav|mp3|mp4|png|jpg|jpeg|gif).*$', '', cleaned, flags=re.MULTILINE)
    
    # Remove excessive whitespace
    cleaned = re.sub(r'\n\s*\n', '\n', cleaned)
    cleaned = cleaned.strip()
    
    return cleaned

def search_similar_precedents(query_text: str,
                             threshold: float = 0.5,
                             limit: int = 3) -> List[Dict[str, Any]]:
    """
    Search for similar precedents using TiDB's native vector search with MySQLdb.
    Uses VEC_COSINE_DISTANCE function for efficient vector similarity search.
    
    Args:
        query_text: Text to search for similar precedents
        threshold: Cosine similarity threshold (0.0 to 1.0, higher=more similar)
        limit: Maximum number of results
        
    Returns:
        List of precedent dictionaries with cosine similarity scores.
    """
    print(f"🔍 [PRECEDENT SEARCH] Starting search for: '{query_text[:100]}...'")
    print(f"📊 [PRECEDENT SEARCH] Parameters: threshold={threshold}, limit={limit}")
    
    try:
        print(_embedding_model)
        if _embedding_model is None:
            raise RuntimeError("Embedding model not initialized. Call initialize_global_clients() first.")
        
        # Generate embedding for the query
        query_embedding = _embedding_model.encode(query_text).tolist()
        
        # Use TiDB's native vector search with VEC_COSINE_DISTANCE
        # Convert threshold to distance (distance = 1 - similarity)
        distance_threshold = 1.0 - threshold
        
        search_sql = """
        SELECT id, description, path, router_format, messages, objective, 
               is_complex, input_type, type_savepoint, created_at,
               VEC_COSINE_DISTANCE(embedding, %s) as distance
        FROM precedent 
        WHERE VEC_COSINE_DISTANCE(embedding, %s) <= %s
        ORDER BY distance ASC
        LIMIT %s
        """
        
        with get_db_connection() as conn:
            with conn.cursor(MySQLdb.cursors.DictCursor) as cur:
                # Convert embedding list to the format TiDB expects for VECTOR column
                embedding_str = json.dumps(query_embedding)
                cur.execute(search_sql, (embedding_str, embedding_str, distance_threshold, limit))
                results = cur.fetchall()
                
        if not results:
            print("📋 [PRECEDENT SEARCH] No similar precedents found")
            return []
        
        print(f"📋 [PRECEDENT SEARCH] Found {len(results)} similar precedents")
        print(results)
        # Convert results to our expected format
        precedents = []
        for i, result in enumerate(results):
            # Convert distance back to similarity score
            distance = float(result['distance'])
            similarity_score = max(0.0, 1.0 - distance)
            
            precedent_dict = {
                "id": result['id'],
                "description": result['description'],
                "path": json.loads(result['path']) if isinstance(result.get('path'), str) else result.get('path'),
                "router_format": json.loads(result['router_format']) if isinstance(result.get('router_format'), str) else result.get('router_format'),
                "messages": result.get('messages', ''),
                "objective": result.get('objective', ''),
                "is_complex": bool(result.get('is_complex', False)),
                "input_type": result.get('input_type', ''),
                "type_savepoint": json.loads(result['type_savepoint']) if isinstance(result.get('type_savepoint'), str) else result.get('type_savepoint', []),
                "created_at": result.get('created_at'),
                "score": similarity_score  # Cosine similarity score (0.0-1.0, higher=better)
            }
            precedents.append(precedent_dict)
            print(f"✅ [PRECEDENT SEARCH] Precedent {i+1}: ID={precedent_dict['id']}, score={precedent_dict['score']:.4f}")
        
        # Apply reranking if available
        if precedents and _reranker:
            print("🔄 [PRECEDENT SEARCH] Applying reranking...")
            precedents = rerank_precedents(query_text, precedents, top_k=limit)
        
        print(f"🎉 [PRECEDENT SEARCH] Search complete! Found {len(precedents)} precedents above threshold")
        return precedents
        
    except Exception as e:
        print(f"❌ [PRECEDENT SEARCH] Error in vector search: {e}")
        raise

def rerank_precedents(query: str, precedents: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """Rerank precedents using the reranker model."""
    if not precedents:
        return precedents[:top_k]
    
    if _reranker is None:
        raise RuntimeError("Reranker not initialized. Call initialize_global_clients() first.")
    
    # Prepare documents for reranking
    documents = [f"{p.get('objective', '')} - {p.get('description', '')}" for p in precedents]
    
    # Rerank using the reranker
    reranked_results = _reranker.rerank(query, documents, top_n=min(top_k, len(documents)))
    print(f"🎉 [PRECEDENT SEARCH] Reranked results:\n{reranked_results}")
    # Return reranked precedents
    reranked_precedents = []
    for result in reranked_results:
        precedent_idx = result.index
        precedent = precedents[precedent_idx].copy()
        precedent['rerank_score'] = result.relevance_score
        reranked_precedents.append(precedent)
    print(f"🎉 [PRECEDENT SEARCH] Reranked precedents:\n{reranked_precedents}")
    return reranked_precedents

def save_workflow_precedent(objective: str,
                           chosen_path: List[Dict[str, Any]],
                           router_format: Dict[str, Any],
                           messages: str,
                           input_type: str,
                           is_complex: bool,
                           type_savepoint: List[str]) -> str:
    """
    Save a new precedent with vector embedding using MySQLdb and TiDB VECTOR column.
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
        ID of created precedent (auto-increment integer as string)
        
    Raises:
        RuntimeError: If embedding model not initialized
        Exception: If database save operation fails
    """
    print(f"💾 [PRECEDENT SAVE] Starting precedent save process...")
    print(f"🎯 [PRECEDENT SAVE] Objective: '{objective[:100]}...'")
    print(f"📊 [PRECEDENT SAVE] Workflow has {len(chosen_path)} steps, input_type: {input_type}, complex: {is_complex}")
    
    if _embedding_model is None:
        raise RuntimeError("Embedding model not initialized. Call initialize_global_clients() first.")
    
    try:
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
        
        # Insert using MySQLdb with TiDB VECTOR column
        insert_sql = """
        INSERT INTO precedent (description, path, router_format, messages, objective, 
                              is_complex, input_type, type_savepoint, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Convert embedding list to JSON string for VECTOR column
                embedding_str = json.dumps(embedding)
                
                cur.execute(insert_sql, (
                    description,  # Store formatted description
                    json.dumps(chosen_path),
                    json.dumps(router_format),
                    messages,
                    objective,
                    is_complex,
                    input_type,
                    json.dumps(type_savepoint),
                    embedding_str  # TiDB VECTOR column accepts JSON string format
                ))
                
                # Get the auto-generated ID
                precedent_id = conn.insert_id()
                
        print(f"✅ [PRECEDENT SAVE] Successfully saved precedent with ID: {precedent_id}")
        print(f"📊 [PRECEDENT SAVE] Document size: text={len(description)} chars")
        return str(precedent_id)
        
    except Exception as e:
        print(f"❌ [PRECEDENT SAVE] Error saving precedent: {e}")
        print(f"🔧 [PRECEDENT SAVE] Failed to save precedent for objective: '{objective[:100]}...'")
        raise