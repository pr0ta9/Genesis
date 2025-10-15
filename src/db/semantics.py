import json
from weaviate.classes.query import Rerank, Filter

def show_all(client, collection_name: str = "precedent"):
    collection = client.collections.get(collection_name)
    all_precedents = []
    for precedent in collection.iterator():
        all_precedents.append(precedent)
    return all_precedents

def search(client, query, rerank_query=None, limit=5, collection_name: str = "precedent"):
    collection = client.collections.get(collection_name)
    response = collection.query.hybrid(
        query=query,
        limit=limit,
        # rerank=Rerank(
        #     prop="description",  # The property to rerank on
        #     query=rerank_query if rerank_query else query  # Use rerank_query if provided, else use the original query
        # )  # Disabled: requires external reranker API
    )
    return response.objects

def _serialize_nested_dicts(obj):
    """Recursively convert dict fields to JSON strings for Weaviate storage."""
    if isinstance(obj, dict):
        return {k: _serialize_nested_dicts(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        result = []
        for item in obj:
            if isinstance(item, dict):
                # Convert dict fields to JSON strings
                serialized = {}
                for k, v in item.items():
                    if k in ('param_types', 'required_inputs', 'default_params', 'param_values'):
                        serialized[k] = json.dumps(v) if isinstance(v, dict) else v
                    else:
                        serialized[k] = _serialize_nested_dicts(v)
                result.append(serialized)
            else:
                result.append(item)
        return result
    else:
        return obj

def _deserialize_nested_dicts(obj):
    """Recursively convert JSON strings back to dicts for Weaviate retrieval."""
    if isinstance(obj, dict):
        return {k: _deserialize_nested_dicts(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        result = []
        for item in obj:
            if isinstance(item, dict):
                # Convert JSON strings back to dicts
                deserialized = {}
                for k, v in item.items():
                    if k in ('param_types', 'required_inputs', 'default_params', 'param_values'):
                        # Try to parse JSON string, fallback to original value
                        if isinstance(v, str):
                            try:
                                deserialized[k] = json.loads(v)
                            except (json.JSONDecodeError, ValueError):
                                deserialized[k] = v
                        else:
                            deserialized[k] = v
                    else:
                        deserialized[k] = _deserialize_nested_dicts(v)
                result.append(deserialized)
            else:
                result.append(item)
        return result
    else:
        return obj

def save(client, data: dict, collection_name: str = "precedent"):
    """
    Save a single object to the 'precedent' collection.
    Converts dict fields (param_types, required_inputs, default_params, param_values) to JSON strings.
    If 'uid' is present in data, it will be used as both the object ID and the uid property.
    :param client: The Weaviate client instance.
    :param data: A dictionary of property values matching the collection schema.
    :return: The UUID of the inserted object.
    """
    # Extract uid if provided (to use as object ID)
    provided_uuid = data.get("uid")
    
    # Serialize nested dicts to JSON strings
    serialized_data = _serialize_nested_dicts(data)
    
    collection = client.collections.get(collection_name)
    
    # Insert with explicit UUID if provided, otherwise let Weaviate generate one
    if provided_uuid:
        uuid = collection.data.insert(properties=serialized_data, uuid=provided_uuid)
    else:
        uuid = collection.data.insert(serialized_data)    
    print(f"🔍 [SEMANTICS] All precedents: {show_all(client)}")
    return uuid

def delete(client, uuid_list: list[str], collection_name: str = "precedent"):
    """
    Delete multiple precedents by their UUIDs.
    :param client: The Weaviate client instance.
    :param uuid_list: A list of UUID strings to delete.
    :param collection_name: The name of the collection (default: "precedent").
    :return: Number of objects deleted.
    """
    
    if not uuid_list:
        return 0
    
    collection = client.collections.get(collection_name)
    try:
        # Use delete_many with filter for batch deletion
        result = collection.data.delete_many(
            where=Filter.by_id().contains_any(uuid_list)
        )
        # result contains information about deletion, including count
        deleted_count = getattr(result, 'successful', len(uuid_list))
        print(f"🗑️ [SEMANTICS] Deleted {deleted_count} precedent(s)")
        return deleted_count
    except Exception as e:
        print(f"Error deleting precedents: {e}")
        return 0
    
def delete_all(client, collection_name: str = "precedent"):
    collection = client.collections.get(collection_name)
    for precedent in collection.iterator():
        collection.data.delete_by_id(precedent.uuid)
    return True
