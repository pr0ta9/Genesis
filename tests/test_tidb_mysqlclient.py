"""
Precedent search and storage using TiDB with mysqlclient.
Handles embedding generation and semantic search for workflow precedents.

Environment Variables Setup:
TIDB_HOST=gateway01.us-east-1.prod.aws.tidbcloud.com
TIDB_PORT=4000
TIDB_USER=UTGS9gKpMKBQEbU.root
TIDB_PASSWORD=<YOUR_PASSWORD>
TIDB_DB_NAME=precedent_db
CA_PATH=<path_to_your_ca_certificate>
"""
import json
import os
import re
from typing import List, Optional, Dict, Any, Tuple
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
project_root = Path(__file__).parent.parent

def get_mysqlclient_connection(autocommit: bool = True) -> MySQLdb.Connection:
    """Create a mysqlclient connection to TiDB."""
    # Get connection parameters from environment variables
    tidb_host = os.environ.get('TIDB_HOST')
    tidb_port = os.environ.get('TIDB_PORT', 4000)
    tidb_user = os.environ.get('TIDB_USERNAME')
    tidb_password = os.environ.get('TIDB_PASSWORD')
    tidb_db_name = os.environ.get('TIDB_DATABASE', 'precedent_db')
    ca_path = os.environ.get('CA')
    print(f"Host: {tidb_host}")
    print(f"Port: {tidb_port}")
    print(f"User: {tidb_user}")
    print(f"Password: {tidb_password}")
    print(f"Database: {tidb_db_name}")
    print(f"CA Path: {ca_path}")
    if not all([tidb_host, tidb_user, tidb_password]):
        raise ValueError(
            "Missing required environment variables. Please set:\n"
            "TIDB_HOST, TIDB_USER, TIDB_PASSWORD, TIDB_DB_NAME, CA_PATH"
        )
    
    # Build connection configuration
    db_conf = {
        "host": tidb_host,
        "port": int(tidb_port),
        "user": tidb_user,
        "password": tidb_password,
        "database": tidb_db_name,
        "autocommit": autocommit,
        "charset": "utf8mb4"
    }
    
    # Add SSL configuration if CA path is provided
    if ca_path:
        db_conf["ssl_mode"] = "VERIFY_IDENTITY"
        db_conf["ssl"] = {"ca": ca_path}
    
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

def create_precedent_table():
    """Create the precedent table if it doesn't exist."""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS precedent (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        content LONGTEXT,
        metadata JSON,
        embedding JSON COMMENT 'Vector embedding stored as JSON array',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_title (title),
        INDEX idx_created_at (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(create_table_sql)
            print("✅ [PRECEDENT] Precedent table created or verified successfully")

def parse_connection_string_to_env_vars(connection_string: str) -> Dict[str, str]:
    """
    Parse a connection string and return environment variables.
    Input: mysql://UTGS9gKpMKBQEbU.root:<PASSWORD>@gateway01.us-east-1.prod.aws.tidbcloud.com:4000/precedent_db
    """
    import re
    pattern = r'mysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)'
    match = re.match(pattern, connection_string)
    
    if not match:
        raise ValueError(f"Invalid connection string format: {connection_string}")
    
    user, password, host, port, database = match.groups()
    
    return {
        'TIDB_HOST': host,
        'TIDB_PORT': port,
        'TIDB_USER': user,
        'TIDB_PASSWORD': password,
        'TIDB_DB_NAME': database
    }

# Initialize components once during startup (called from main.py)
def initialize_global_clients():
    """Initialize global database connection, reranker, and embedding model once during startup."""
    global _reranker, _embedding_model
    
    print("🔧 [PRECEDENT] Initializing global precedent clients...")
    
    # # Check if we have a connection string to parse
    # connection_string = os.environ.get('TIDB_CONNECTION_STRING')
    # if connection_string:
    #     print("🔗 [PRECEDENT] Parsing connection string to environment variables...")
    #     env_vars = parse_connection_string_to_env_vars(connection_string)
    #     for key, value in env_vars.items():
    #         if not os.environ.get(key):  # Don't overwrite existing env vars
    #             os.environ[key] = value
    #     print(f"✅ [PRECEDENT] Parsed connection: {env_vars['TIDB_USER']}@{env_vars['TIDB_HOST']}:{env_vars['TIDB_PORT']}/{env_vars['TIDB_DB_NAME']}")
    
    # Test the database connection
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DATABASE() as current_db")
                current_db = cur.fetchone()[0]
                print(f"✅ [PRECEDENT] Connected to TiDB database: {current_db}")
                
                # Check if precedent table exists
                cur.execute("SHOW TABLES LIKE 'precedent'")
                table_exists = cur.fetchone() is not None
                print(f"📋 [PRECEDENT] Precedent table exists: {table_exists}")
                
                # Create table if it doesn't exist
                if not table_exists:
                    print("🔧 [PRECEDENT] Creating precedent table...")
                    create_precedent_table()
                    
    except Exception as e:
        print(f"❌ [PRECEDENT] Database connection failed: {e}")
        raise
    
    if _reranker is None:
        print("🔧 [PRECEDENT] Loading reranker model: jina_ai/jina-reranker-v1-tiny-en...")
        _reranker = Reranker(model_name="jina_ai/jina-reranker-v1-tiny-en")
        print("✅ [PRECEDENT] Reranker initialized successfully")
    
    if _embedding_model is None:
        print("🔧 [PRECEDENT] Loading embedding model: all-MiniLM-L6-v2...")
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        print("✅ [PRECEDENT] Embedding model initialized successfully")
    
    print("🎉 [PRECEDENT] All global clients initialized successfully!")

# CRUD Operations using mysqlclient

def create_precedent(title: str, description: str, content: str, metadata: Dict[str, Any] = None) -> int:
    """Create a new precedent with embedding and return its ID."""
    # Generate embedding for the content
    embedding = _embedding_model.encode(content).tolist()
    
    insert_sql = """
    INSERT INTO precedent (title, description, content, metadata, embedding)
    VALUES (%s, %s, %s, %s, %s)
    """
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(insert_sql, (
                title,
                description,
                content,
                json.dumps(metadata or {}),
                json.dumps(embedding)
            ))
            precedent_id = conn.insert_id()
            print(f"✅ [PRECEDENT] Created precedent with ID: {precedent_id}")
            return precedent_id

def get_precedent_by_id(precedent_id: int) -> Optional[Dict[str, Any]]:
    """Get a precedent by its ID."""
    select_sql = "SELECT * FROM precedent WHERE id = %s"
    
    with get_db_connection() as conn:
        with conn.cursor(MySQLdb.cursors.DictCursor) as cur:
            cur.execute(select_sql, (precedent_id,))
            result = cur.fetchone()
            if result:
                # Parse JSON fields
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                if result['embedding']:
                    result['embedding'] = json.loads(result['embedding'])
            return result

def search_precedents_by_text(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search for precedents using text search (simple LIKE query)."""
    search_sql = """
    SELECT * FROM precedent 
    WHERE title LIKE %s OR description LIKE %s OR content LIKE %s
    ORDER BY created_at DESC
    LIMIT %s
    """
    
    search_pattern = f"%{query}%"
    
    with get_db_connection() as conn:
        with conn.cursor(MySQLdb.cursors.DictCursor) as cur:
            cur.execute(search_sql, (search_pattern, search_pattern, search_pattern, limit))
            results = cur.fetchall()
            
            # Parse JSON fields for each result
            for result in results:
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                if result['embedding']:
                    result['embedding'] = json.loads(result['embedding'])
            
            return list(results)

def get_all_precedents(limit: int = 100) -> List[Dict[str, Any]]:
    """Get all precedents (for vector similarity search)."""
    select_sql = "SELECT * FROM precedent ORDER BY created_at DESC LIMIT %s"
    
    with get_db_connection() as conn:
        with conn.cursor(MySQLdb.cursors.DictCursor) as cur:
            cur.execute(select_sql, (limit,))
            results = cur.fetchall()
            
            # Parse JSON fields for each result
            for result in results:
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                if result['embedding']:
                    result['embedding'] = json.loads(result['embedding'])
            
            return list(results)

def search_precedents_by_similarity(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search for precedents using semantic similarity."""
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    
    # Generate embedding for the query
    query_embedding = _embedding_model.encode(query)
    
    # Get all precedents (you might want to implement this more efficiently)
    all_precedents = get_all_precedents()
    
    if not all_precedents:
        return []
    
    # Calculate similarities
    similarities = []
    for precedent in all_precedents:
        if precedent['embedding']:
            precedent_embedding = np.array(precedent['embedding'])
            similarity = cosine_similarity([query_embedding], [precedent_embedding])[0][0]
            similarities.append((similarity, precedent))
    
    # Sort by similarity and return top results
    similarities.sort(reverse=True, key=lambda x: x[0])
    top_results = similarities[:limit]
    
    return [precedent for _, precedent in top_results]

def update_precedent(precedent_id: int, title: str = None, description: str = None, 
                    content: str = None, metadata: Dict[str, Any] = None) -> bool:
    """Update a precedent."""
    updates = []
    params = []
    
    if title is not None:
        updates.append("title = %s")
        params.append(title)
    
    if description is not None:
        updates.append("description = %s")
        params.append(description)
    
    if content is not None:
        updates.append("content = %s")
        params.append(content)
        # Regenerate embedding if content is updated
        embedding = _embedding_model.encode(content).tolist()
        updates.append("embedding = %s")
        params.append(json.dumps(embedding))
    
    if metadata is not None:
        updates.append("metadata = %s")
        params.append(json.dumps(metadata))
    
    if not updates:
        return False
    
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(precedent_id)
    
    update_sql = f"UPDATE precedent SET {', '.join(updates)} WHERE id = %s"
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            rows_affected = cur.execute(update_sql, params)
            return rows_affected > 0

def delete_precedent(precedent_id: int) -> bool:
    """Delete a precedent."""
    delete_sql = "DELETE FROM precedent WHERE id = %s"
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            rows_affected = cur.execute(delete_sql, (precedent_id,))
            return rows_affected > 0

def count_precedents() -> int:
    """Get the total count of precedents."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM precedent")
            return cur.fetchone()[0]

# Utility functions for working with embeddings and reranking
def rerank_precedents(query: str, precedents: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
    """Rerank precedents using the reranker model."""
    if not precedents or not _reranker:
        return precedents[:top_k]
    
    # Prepare documents for reranking
    documents = [f"{p['title']} - {p['description']}" for p in precedents]
    
    # Rerank using the reranker
    reranked_results = _reranker.rerank(query, documents, top_k=min(top_k, len(documents)))
    
    # Return reranked precedents
    reranked_precedents = []
    for result in reranked_results:
        precedent_idx = result['index']
        precedent = precedents[precedent_idx].copy()
        precedent['rerank_score'] = result['score']
        reranked_precedents.append(precedent)
    
    return reranked_precedents

# Initialize on import (you might want to call this explicitly instead)
initialize_global_clients()
select_sql = "DESCRIBE precedent"

with get_db_connection() as conn:
    with conn.cursor(MySQLdb.cursors.DictCursor) as cur:
        cur.execute(select_sql)
        result = cur.fetchone()
        if result:
            print(result)
