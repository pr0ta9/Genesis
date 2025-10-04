from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchResults, BraveSearch
from langchain_community.utilities import GoogleSerperAPIWrapper

import os

@tool
def search(query: str, max_results: int = 5, engine: str = "duckduckgo") -> str:
    """Search Web for information."""
    if engine == "duckduckgo":
        ddg_tool = DuckDuckGoSearchResults(max_results=max_results, backend="api")
        return ddg_tool.run({"query": query})
    elif engine == "brave":
        brave_tool = BraveSearch.from_api_key(api_key=os.getenv("BRAVE_API_KEY"), search_kwargs={"count": max_results})
        return brave_tool.run({"query": query})
    elif engine == "google":
        search = GoogleSerperAPIWrapper(serper_api_key=os.getenv("SERPER_API_KEY"))
        return search.run(query)
    else:
        raise ValueError(f"Invalid engine: {engine}")


