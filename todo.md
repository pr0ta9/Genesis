# Genesis AI Assistant - Development TODO

---

## 🐛 Bug Fixes

### 1. Precedent Score Fix
**Issue**: All precedent scores showing 0.0 instead of actual similarity scores

**Location**: `src/orchestrator/core/orchestrator.py` (lines 102-115)

**What to Change**: 
- Debug Weaviate hybrid search response structure to identify correct score attribute
- Update score extraction logic from `result.metadata.score/certainty/distance` to correct attribute
- Add logging to verify non-zero scores are returned

---

## ⚡ Optimizations

### 1. Agent Prompt Optimization
**Goal**: Reduce token usage, improve performance, eliminate repetition

**Locations**:
- `src/orchestrator/agents/prompts/Classifier.yaml` (87 lines, too verbose)
- `src/orchestrator/agents/prompts/Router.yaml` (226+ lines, excessive detail)
- `src/orchestrator/agents/prompts/Precedent.yaml`
- `src/orchestrator/agents/prompts/Finalizer.yaml`

**What to Change**:
- Extract common data type definitions into shared template
- Remove redundant examples and verbose explanations
- Condense file reference system documentation in Router.yaml
- Eliminate repetitive reasoning instructions across all prompts

---

### 2. LLM Parameter Tuning
**Goal**: Optimize temperature, context window, and model parameters per agent type

**Locations**:
- `src/orchestrator/agents/llm.py` (lines 5-23)
- `src/orchestrator/core/orchestrator.py` (line 33)

**What to Change**:
- Test and set optimal temperature per agent: Classifier/Precedent (0.0-0.2), Router (0.3-0.5), Finalizer (0.5-0.8)
- Evaluate num_ctx values (test 8192, 16384, 32768) for performance vs accuracy
- Test repeat_penalty values (current 1.5, test 1.0-2.0 range)
- Add configurable parameters to orchestrator initialization
- Create configuration file for easy tuning without code changes

---

### 3. Multi-Path Execution Optimization (is_partial)
**Goal**: Improve workflow efficiency when parameters are incomplete

**Locations**:
- `src/orchestrator/agents/router.py` (lines 274-297, 312-313)
- `src/orchestrator/executor/executor.py`
- `src/orchestrator/core/state.py`

**What to Change**:
- Add execution state caching to avoid re-routing from scratch
- Implement automatic parameter inference from previous step outputs
- Add "resume" capability without full path regeneration
- Store partial execution context persistently in state
- Add smart parameter suggestion based on execution history

---

### 4. Frontend Layout Optimization
**Goal**: Improve UI responsiveness and user experience

**Locations**:
- `gui/lib/layout.dart` (main layout with sidebar and panels)
- `gui/lib/widgets/chat_panel.dart`
- `gui/lib/widgets/execution_panel.dart`
- `gui/lib/widgets/chat/sidebar.dart`

**What to Change**:
- Improve responsive design for different screen sizes
- Add keyboard shortcuts for panel toggling
- Persist panel states across sessions using SharedPreferences
- Implement dark mode support
- Add smoother animation transitions for panel operations

---

### 5. StructuredData Type Hierarchy
**Goal**: Create specialized data type classes for better path routing

**Location**: `src/orchestrator/path/metadata.py` (lines 110-131)

**What to Change**:
- Make StructuredData a parent class with subclasses:
  - `TableData` - CSV, Excel sheets, database results
  - `JsonData` - Generic JSON/dictionary data
  - `TreeData` - XML, YAML, nested JSON
  - `GraphData` - Network/graph structures
  - `TimeSeriesData` - Time-indexed data
  - `FormData` - Form/survey responses
- Add validation methods per subclass
- Update `src/orchestrator/agents/prompts/Classifier.yaml` with new type definitions

---

### 6. Agents' Web Search Ability
**Goal**: Improve agents' capability to use web search tools effectively

**Locations**:
- `src/orchestrator/tools/agent_tools/web_search.py` (current implementation)
- `src/orchestrator/agents/llm.py` (line 34, tool binding)
- `src/orchestrator/agents/base_agent.py` (agent invocation logic)

**What to Change**:
- Enhance web search tool with better query formulation
- Add search result parsing and summarization
- Improve tool calling logic for agents to know when to use search
- Add search result caching to avoid redundant queries
- Update agent prompts to better leverage search capabilities

---

### 7. Self-Assessment Agent
**Goal**: Add agent or optimize finalizer to evaluate if workflow successfully completed user's request

**Locations**:
- Create `src/orchestrator/agents/assessor.py` (new agent)
- Create `src/orchestrator/agents/prompts/Assessor.yaml` (prompt template)
- Modify `src/orchestrator/core/orchestrator.py` (add assessment node after finalizer)
- Modify `src/orchestrator/core/state.py` (add assessment fields)

**What to Add**:
- New assessment agent that reviews execution results against original user request
- Compare user objective with actual outputs produced
- Check if execution errors occurred that prevented completion
- Verify output files exist and match expected types
- Return assessment score (0-100), success boolean, and reasoning
- Trigger retry or clarification if assessment score is low (<70)
- Update state with assessment results for precedent learning

---

## ✨ New Features

### 1. Add More Processing Tools
**Goal**: Expand tool ecosystem for richer workflows

**Location**: Create new files in `src/orchestrator/tools/path_tools/`

**What to Add**:
- Image tools: resize/compress, style transfer, captioning, QR code generation
- Audio tools: format conversion, splitting/merging, speech-to-text
- Document tools: PDF generation, DOCX/XLSX parsing
- Video tools: frame extraction
- Each tool needs `@genesis_tool` decorator with proper WorkflowType input/output definitions

---

### 2. Frontend Settings Page
**Goal**: Create comprehensive settings UI for configuration

**Location**: Create new files:
- `gui/lib/widgets/settings_page.dart` (main settings UI)
- `gui/lib/data/services/settings_service.dart` (persistence layer)

**What to Add**:
- Connection settings: API URL, timeout, retry behavior
- Appearance: theme selection (light/dark), font size, UI density
- Behavior: auto-scroll, notifications, file size limits
- Advanced: debug logging, cache management, export/import settings
- Use SharedPreferences for persistence
- Add settings button to sidebar in `gui/lib/widgets/chat/sidebar.dart`

---

### 3. Model Selection API & GUI
**Goal**: Allow users to select and switch LLM models

**Backend Location**: Create/enhance:
- `src/api/model.py` (add list and switch endpoints)
- Add `GET /api/v1/models` - list available Ollama models
- Add `POST /api/v1/models/select` - switch active model

**Frontend Location**: Create:
- `gui/lib/widgets/model_selector.dart` (selection widget)
- `gui/lib/data/services/model_service.dart` (API client)

**What to Add**:
- Model dropdown showing available models with capabilities
- Current active model indicator
- Model switching with loading state and error handling
- Integration with settings page or chat panel

---

### 4. Precedent Management UI
**Goal**: Interface for viewing, searching, and managing saved workflows

**Backend Location**: Create endpoints in `src/api/precedent.py`:
- `GET /api/v1/precedents` - list all precedents
- `GET /api/v1/precedents/{id}` - get details
- `DELETE /api/v1/precedents/{id}` - delete precedent
- `PUT /api/v1/precedents/{id}` - update metadata
- `GET /api/v1/precedents/stats` - usage analytics

**Frontend Location**: Create:
- `gui/lib/widgets/precedent_panel.dart` (main management UI)
- `gui/lib/widgets/precedent_list_item.dart` (list view)
- `gui/lib/widgets/precedent_detail_view.dart` (detail page)

**What to Add**:
- List view with search/filter/sort functionality
- Detail view showing workflow path, objective, types, creation date
- Delete with confirmation dialog
- Analytics dashboard showing usage statistics
- Export/import functionality

---

### 5. Agent Tool for Coding
**Goal**: Enable agents to write code to solve tasks dynamically

**Location**: Create new file `src/orchestrator/tools/agent_tools/code_generator.py`

**What to Add**:
- Agent tool that takes task description and generates Python/JavaScript/etc code
- Integration with LLM for code generation based on requirements
- Code validation and syntax checking before returning
- Support for multiple programming languages
- Return generated code as Text or TextFile type
- Add to tool registry for use in workflows

---

### 6. Agent Tool for Create Path Tool
**Goal**: Enable agents to dynamically create new path tools based on requirements

**Location**: Create new file `src/orchestrator/tools/agent_tools/tool_creator.py`

**What to Add**:
- Agent tool that generates new @genesis_tool decorated functions
- Takes tool specification (name, input/output types, description, parameters)
- Generates proper Python code with metadata and function implementation
- Validates generated tool code and registers it dynamically
- Saves generated tool to `src/orchestrator/tools/path_tools/generated/`
- Adds tool to registry without requiring restart

---

### 7. Agent Tool for Code Execution
**Goal**: Execute agent-generated code in isolated environment

**Location**: Create new file `src/orchestrator/tools/agent_tools/code_executor.py`

**What to Add**:
- Similar to current executor in `src/orchestrator/executor/process_isolation.py`
- Takes code string (Python/JavaScript/etc) and executes it in tmp directory
- Write code to temporary file in `tmp/` directory
- Execute in isolated subprocess with timeout and resource limits
- Capture stdout, stderr, and return value
- Clean up temporary files after execution
- Support for different languages (Python, JavaScript, shell scripts)
- Return execution results with success/error status

---

### 8. App Packaging & 1-Click Setup
**Goal**: Make Genesis accessible to non-developers with easy installation

**Location**: Create new directories and files:
- `installers/windows/setup.bat` - Windows installer script
- `installers/windows/genesis-installer.nsi` - NSIS installer config
- `installers/macos/setup.sh` - macOS setup script
- `installers/linux/genesis.appimage.yml` - AppImage config
- `scripts/build-all-platforms.sh` - Build automation

**What to Create**:

**Windows**:
- Installer bundling Flutter executable, Docker Desktop, Ollama
- Portable ZIP version with batch scripts
- Auto-update mechanism

**macOS**:
- .dmg installer with .app bundle
- Homebrew formula for package managers

**Linux**:
- AppImage (universal), Flatpak, Snap packages
- .deb and .rpm packages for distributions

**Setup Scripts**:
- Unified setup with automatic dependency detection
- Guided installation with progress indicators
- Automatic model download and configuration
- First-run wizard
- System tray icon for service management

---

## 📊 Summary

- **Bug Fixes**: 1 item
- **Optimizations**: 7 items  
- **New Features**: 8 items

**Total**: 16 tasks

---

**Last Updated**: 2025-10-04