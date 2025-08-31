# Genesis To-do List

## Agents
**1.** Set up baseAgent class `🔥 Critical`
- **1.1** Set up __init__ ✅
- **1.2** Set up prompt loading ✅
- **1.3** Set up invoke `⚡ High` *depends on: 5.2*
- **1.4** Create abstract method ✅

**2.** Set up Classifier Agent `⚡ High`
- **2.1** Set up ClassificationResponse model `⚡ High` ✅
- **2.2** Set up Classifier.yaml prompt template `⚡ High` *depends on: 5.2*
- **2.3** Set up __init__ ✅
- **2.4** Set up classify method `⚡ High` *depends on: 2.1, 2.2, 5.2*
- **2.5** Set up get_next_step `📋 Medium` *depends on: 2.4*

**3.** Set up Router Agent `⚡ High`
- **3.1** Set up RoutingResponse model `⚡ High` ✅
- **3.2** Set up Router.yaml prompt template `⚡ High` *depends on: 4.0*
- **3.3** Set up __init__ ✅
- **3.4** Set up route method `⚡ High` *depends on: 3.1, 3.2, 4.0*
- **3.5** Set up get_next_step `📋 Medium` *depends on: 3.4*

**4.** Set up Finalizer Agent `⚡ High`
- **4.1** Set up FinalizationResponse model `⚡ High`
- **4.2** Set up Finalizor.yaml prompt template `⚡ High` *depends on: 6.0*
- **4.3** Set up __init__ ✅
- **4.4** Set up finalize method `⚡ High` *depends on: 4.1, 4.2, 5.2*
- **4.5** Set up get_next_step `📋 Medium` *depends on: 4.4*

## Path
**5.** Set up Path System (Type-based routing and path discovery) `🔥 Critical`
- **5.1** Set up decorators.py - @tool decorator for input/output type declaration `🔥 Critical` ✅
    - **5.1.1** Fix @tool decorator to some other name `🔥 Critical` ✅
- **5.2** Set up metadata.py - WorkflowType, FileType system, ToolMetadata `🔥 Critical` *depends on: 5.1* ✅
    - **5.2.1** Finalize TypeClass `🔥 Critical` ✅
- **5.3** Set up registry.py - Tool discovery and type→tools index `🔥 Critical` *depends on: 5.2, 7.1*
- **5.4** Set up generator.py - DFS path planning with type compatibility `🔥 Critical` *depends on: 5.3, 7.1*

## Executor
**6** Set up Executor System (executable path) `🔥 Critical`
- **6.1** Set up flow_state.py - StateGenerator for TypedDict schemas `🔥 Critical` *depends on: 5.0*
- **6.2** Set up conversion.py - StateGraphConverter for LangGraph compilation `🔥 Critical` *depends on: 11.1*
- **6.3** Set up execution.py - GraphExecutor and ExecutionOrchestrator `🔥 Critical` *depends on: 11.2*

## Tools
**7.** Set up Tools Infrastructure `⚡ High`
- **7.1** Set up Path Tools (Type transformation tools) `⚡ High`
  - **7.1.1** Set up base tool interface with input_type → output_type signature `🔥 Critical` *depends on: 5.2*
  - **7.1.2** Implement OCR tool (image→text) `📋 Medium` *depends on: 7.1.1*
  - **7.1.3** Implement translator tool (text→text) `📋 Medium` *depends on: 7.1.1*
  - **7.1.4** Implement audio transcriber (audio→text) `📋 Medium` *depends on: 7.1.1*
  - **7.1.5** Set up overlay tools `💡 Low` *depends on: 7.1.1*
  - **7.1.6** Implement denoise tool (audio→audio) `💡 Low` *depends on: 7.1.1*
  - **7.1.7** Implement get_pdf_form_field `💡 Low` *depends on: 7.1.1*
  - **7.1.8** Implement fill pdf form `💡 Low` *depends on: 7.1.1*

- **7.2** Set up Agent Tools (Utility tools for agent reasoning) `⚡ High`
  - **7.2.1** Set up web search tool `⚡ High`
  - **7.2.2** Set up calculator tool `📋 Medium`

## GUI
**8.** Set up GUI System `💡 Low`
- **8.1** Set up basic interface framework `💡 Low`
- **8.2** Implement user input handling `💡 Low` *depends on: 8.1*
- **8.3** Set up progress display `💡 Low` *depends on: 8.1*
- **8.4** Implement result presentation `💡 Low` *depends on: 8.1*
- **8.5** Set up controller bridge to core logic `💡 Low` *depends on: 9.5*
- **8.6** Add simple mode vs developer mode toggle `💡 Low` *depends on: 8.5*

## Orchestrator
**9.** Set up Main Orchestrator `🔥 Critical`
- **9.1** Set up agent coordination flow `🔥 Critical` *depends on: 2.0, 3.0, 4.0*
- **9.2** Set up path finding integration `🔥 Critical` *depends on: 5.0*
- **9.3** Set up execution coordination `🔥 Critical` *depends on: 6.0*
- **9.4** Set up validation pipeline `⚡ High` *depends on: 4.0*
- **9.5** Implement main pipeline controller `🔥 Critical` *depends on: 9.1, 9.2, 9.3, 9.4*

## Main
**10.** Project Foundation `🔥 Critical`
- **10.1** Check current environment (check for venv and prepare for automated setup if missing) `🔥 Critical` *depends on: everything else*
- **10.2** Create requirements.txt `🔥 Critical` *depends on: 10.1*
- **10.3** Initialize project structure `🔥 Critical` *depends on: 10.1*
- **10.4** Create README.md `📋 Medium`

## Data Management
**12.** Set up Data & Templates `💡 Low`
- **12.1** Set up templates directory structure `💡 Low`
- **12.2** Implement successful path pattern storage `💡 Low` *depends on: 5.0*
- **12.3** Set up runtime path caching `💡 Low` *depends on: 12.2*
- **12.4** Create cache management utilities `💡 Low` *depends on: 12.3*

## Testing
**13.** Set up Testing Infrastructure `💡 Low`
- **13.1** Set up unit test framework `💡 Low`
- **13.2** Test path generation `💡 Low` *depends on: 5.0*
- **13.3** Test execution `💡 Low` *depends on: 7.0*
- **13.4** Test agent interactions `💡 Low` *depends on: 2.0, 3.0, 4.0*
- **13.4** Set up end-to-end workflow tests `💡 Low` *depends on: 9.5*

---

## 🏷️ Priority Legend
- 🔥 **Critical** - Must complete first, blocks other work
- ⚡ **High** - Important for core functionality
- 📋 **Medium** - Standard features and improvements  
- 💡 **Low** - Nice-to-have features and optimizations

## 🔗 Dependency Reference System
- Use task numbers (e.g., `5.2`) to reference specific subtasks
- Use section numbers (e.g., `5.0`) to reference completion of entire section
- Dependencies marked as `*depends on: X.Y*` cannot start until those tasks complete

---
*Last updated: Genesis Project - Structured Dependencies*

