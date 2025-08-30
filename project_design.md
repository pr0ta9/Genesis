# Genesis Minimal Project Structure

## Project Root Structure
```
yoruzuya/
├── src/
│   ├── path/                    
│   │   └── # Type system + Path generation + Graph construction + Path finding algorithms
│   │
│   ├── executor/                
│   │   └── # Path execution engine + State management between tools
│   │
│   ├── tools/                   
│   │   ├── path_tools/         
│   │   │   └── # Tools used in path execution (OCR, translate, overlay, converters, etc.)
│   │   │       # These are the type-transforming tools (input_type → output_type)
│   │   │
│   │   └── agent_tools/        
│   │       └── # Tools agents use directly (web search, calculator, file operations, etc.)
│   │           # These are utility tools for agent reasoning/decision-making
│   │
│   ├── agents/                  
│   │   └── # Task analyzer, Path selector, Result validator agents
│   │
│   ├── gui/                     
│   │   └── # User interface + Controller bridge to core logic
│   │
│   └── orchestrator.py         
│
├── tests/                       
│   └── # Integration and unit tests
│
├── data/                        
│   ├── templates/              
│   │   └── # Stored successful path patterns
│   └── cache/                  
│       └── # Runtime path cache
│
├── main.py                     
├── requirements.txt
└── README.md
```

## Directory Purposes

### **`src/tools/path_tools/`**
- Tools that transform data from one type to another
- Each tool has clear input_type → output_type signature
- Used exclusively in path execution chains
- Examples: OCR (image→text), translator (text→text), audio transcriber (audio→text)
- These tools are nodes in your type transformation graph

### **`src/tools/agent_tools/`**
- Tools that agents call directly for reasoning or gathering information
- Don't necessarily fit the type transformation model
- Used for agent decision-making, not path execution
- Examples: web search, RAG retrieval, calculator, system commands, API calls
- These help agents make decisions but aren't part of the execution path

### **`src/path/`**
- Type definitions and detection logic
- Graph construction from path_tools
- Path finding algorithms (BFS/DFS)
- Path caching mechanisms
- Note: Only uses tools from `path_tools/`, never from `agent_tools/`

### **`src/executor/`**
- Executes chains of path_tools in sequence
- Manages state/data flow between path_tools
- Error handling and recovery during execution
- Progress tracking and reporting
- Note: Only executes path_tools, agents use agent_tools separately

### **`src/agents/`**
- Analyzer: Uses agent_tools to understand user query and detect types
- Selector: Uses agent_tools to choose between multiple valid paths
- Validator: Uses agent_tools to verify if execution results meet user needs
- Can directly call agent_tools but orchestrates path_tools through executor

### **`src/orchestrator.py`**
- Coordinates the flow: agents → path finding → execution → validation
- Bridge between agent reasoning and path execution
- Manages when to use agent_tools vs when to execute path_tools
- Main pipeline controller

This separation makes it clear that:
1. **Path tools** are deterministic type transformers used in execution chains
2. **Agent tools** are utilities for LLM reasoning and decision-making
3. Agents can use agent_tools directly but interact with path_tools only through the executor