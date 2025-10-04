import 'package:flutter/material.dart';
import 'package:gui/data/services/streaming_service.dart';
import 'package:gui/widgets/execution/propagation.dart';
import 'package:gui/widgets/execution/pipeline.dart';
import 'package:gui/widgets/execution/code_block.dart';
import 'package:gui/widgets/execution/console.dart';
import 'package:gui/widgets/execution/preview.dart';
import 'package:gui/widgets/common/resizable_divider.dart';

class ExecutionPanel extends StatefulWidget {
  final StreamingService? streamingService;
  final String? chatId;
  final String? staticExecutionOutputPath; // Execution output path from state
  
  // Static data for stored messages
  final WorkflowState? staticWorkflowState;
  final List<List<String>>? staticAllPaths;
  final List<String>? staticChosenPath;
  final String? staticExecutingNodeId;
  
  // Workflow type information (for endpoint construction)
  final String? inputType;  // e.g., "AUDIO", "IMAGE", "TEXT"
  final String? outputType; // e.g., "AUDIO", "IMAGE", "TEXT"
  
  // Callback for closing/collapsing the panel
  final VoidCallback? onClose;

  const ExecutionPanel({
    Key? key,
    this.streamingService,
    this.chatId,
    this.staticExecutionOutputPath,
    this.staticWorkflowState,
    this.staticAllPaths,
    this.staticChosenPath,
    this.staticExecutingNodeId,
    this.inputType,
    this.outputType,
    this.onClose,
  }) : super(key: key);

  @override
  State<ExecutionPanel> createState() => _ExecutionPanelState();
}

class _ExecutionPanelState extends State<ExecutionPanel> {
  WorkflowState? _currentWorkflow;
  List<List<String>> _allPaths = [];
  List<String>? _chosenPath;
  String? _executingNodeId;
  
  // Execution output path from state (for static messages)
  String? _executionOutputPath;
  
  // Workflow type information (for endpoint construction in visualization)
  String? _inputType;
  String? _outputType;
  
  // Shared animation state (like NextJS frontend)
  List<List<String>> _currentPaths = []; // UI-ephemeral paths during animation
  String _animationMode = 'find_path'; // 'find_path', 'reduce', 'chosen_path'
  int _currentPathIndex = 0;
  bool _populateCompleted = false;
  bool _reduceStarted = false;
  
  // Selected execution step state (for CodeBlock/Console/Preview)
  // This is what the user is currently viewing (can be manually selected or auto-selected)
  String? _selectedToolName;
  int? _selectedStepIndex;
  
  // Current executing tool (updated in background during streaming)
  // Used to track which tool is executing, but display is driven by _selectedToolName
  String? _currentExecutingTool;
  
  // Track if route has completed (to show codeblock/console/preview)
  bool _showExecutionDetails = false;
  
  // References to child components for animation control (unique per instance)
  late final GlobalKey<State<Propagation>> _propagationKey;
  late final GlobalKey<State<Pipeline>> _pipelineKey;

  @override
  void initState() {
    super.initState();
    // Initialize unique GlobalKeys to prevent duplication errors
    _propagationKey = GlobalKey<State<Propagation>>(debugLabel: 'Propagation_${widget.chatId}');
    _pipelineKey = GlobalKey<State<Pipeline>>(debugLabel: 'Pipeline_${widget.chatId}');
    _initializeData();
  }

  @override
  void didUpdateWidget(ExecutionPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    
    // Check for major changes that require full refresh
    final chatChanged = oldWidget.chatId != widget.chatId;
    final streamingModeChanged = (oldWidget.streamingService != null) != (widget.streamingService != null);
    final staticDataChanged = 
      oldWidget.staticAllPaths != widget.staticAllPaths ||
      oldWidget.staticChosenPath != widget.staticChosenPath ||
      oldWidget.staticWorkflowState != widget.staticWorkflowState ||
      oldWidget.staticExecutingNodeId != widget.staticExecutingNodeId;
    
    // Full refresh when chat changes or switching between static/streaming modes
    if (chatChanged || streamingModeChanged) {
      _fullRefresh();
    } else if (staticDataChanged) {
      _initializeData();
    }
  }
  
  /// Full refresh of the execution panel (like other layout components)
  void _fullRefresh() {
    // Reinitialize with new data directly (avoid intermediate empty state)
    _initializeData();
  }

  void _initializeData() {
    // Clean initialization for execution panel
    
    // Use static data if provided (for stored messages)
    if (widget.staticWorkflowState != null || 
        widget.staticAllPaths != null || 
        widget.staticChosenPath != null) {
      setState(() {
        _currentWorkflow = widget.staticWorkflowState;
        _allPaths = widget.staticAllPaths ?? [];
        _chosenPath = widget.staticChosenPath;
        _executingNodeId = widget.staticExecutingNodeId;
        
        // Get type information for endpoint construction
        _inputType = widget.inputType;
        _outputType = widget.outputType;
        
        // Reset selected tool when loading static data
        _selectedToolName = null;
        _selectedStepIndex = null;
        
        // Show execution details for static data only if there's a chosen path
        _showExecutionDetails = _chosenPath != null && _chosenPath!.isNotEmpty;
        
        // For static data: prioritize chosen path over all paths
        if (_chosenPath != null && _chosenPath!.isNotEmpty) {
          // Show only chosen path if available
          _currentPaths = [_chosenPath!];
          _animationMode = 'chosen_path';
          _populateCompleted = true;
          _currentPathIndex = 1;
          _reduceStarted = false;
            } else {
          // No chosen path: show all paths for animation
          _currentPaths = List<List<String>>.from(_allPaths);
          _animationMode = 'find_path';
          _populateCompleted = true; // Mark as completed for static display
          _currentPathIndex = _allPaths.length;
          _reduceStarted = false;
        }
      });
      
      // Use static execution output path if provided
      if (widget.staticExecutionOutputPath != null) {
        _executionOutputPath = widget.staticExecutionOutputPath;
      }
    } else {
      // Reset all state for streaming mode
      setState(() {
        _currentWorkflow = null;
        _allPaths = [];
        _chosenPath = null;
        _executingNodeId = null;
        _executionOutputPath = null;
        _inputType = null;
        _outputType = null;
        _currentPaths = [];
        _animationMode = 'find_path';
        _currentPathIndex = 0;
        _populateCompleted = false;
        _reduceStarted = false;
        
        // Reset selected tool state
        _selectedToolName = null;
        _selectedStepIndex = null;
        
        // Reset executing tool
        _currentExecutingTool = null;
        
        // Reset execution details visibility
        _showExecutionDetails = false;
      });
      _setupStreamingListeners();
    }
  }

  void _setupStreamingListeners() {
    if (widget.streamingService == null) {
      return;
    }
    
    // FIRST: Extract type information from current state (set by classify)
    // This must happen BEFORE using cached paths, so Propagation has correct endpoint types
    final currentState = widget.streamingService!.currentState;
    if (currentState != null) {
      final inputType = currentState['input_type']?.toString().toUpperCase();
      final typeSavepoint = currentState['type_savepoint'];
      final outputType = (typeSavepoint is List && typeSavepoint.isNotEmpty)
          ? typeSavepoint.last.toString().toUpperCase()
          : null;
      
      setState(() {
        _inputType = inputType;
        _outputType = outputType;
      });
    }
    
    // THEN: Check if there's a cached pathDiscovery (for late subscribers)
    final lastPaths = widget.streamingService!.lastPathDiscovery;
    if (lastPaths != null && lastPaths.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {
            _allPaths = lastPaths;
            _currentPaths = [];
            _animationMode = 'find_path';
            _currentPathIndex = 0;
            _populateCompleted = false;
            _reduceStarted = false;
          });
          
          final propagationState = _propagationKey.currentState;
          if (propagationState != null) {
            (propagationState as dynamic).startPathAnimation(lastPaths);
          }
        }
      });
    }
    
    // Check if there's a current executing tool (for late subscribers)
    final currentTool = widget.streamingService!.currentExecutingTool;
    final currentStepIndex = widget.streamingService!.currentStepIndex;
    if (currentTool != null) {
      setState(() {
        _currentExecutingTool = currentTool;
        // Auto-select the currently executing tool if no manual selection exists
        if (_selectedToolName == null && currentStepIndex != null) {
          _selectedToolName = currentTool;
          _selectedStepIndex = currentStepIndex;
          debugPrint('🎯 EXECUTION: Late subscriber - auto-selected currently executing tool: $currentTool (step $currentStepIndex)');
        }
      });
    }

    // Listen to workflow updates
    widget.streamingService!.workflow.listen((workflow) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {
            _currentWorkflow = workflow;
            
            // Extract execution_output_path and type information from streaming state
            final currentState = widget.streamingService?.currentState;
            if (currentState != null) {
              _executionOutputPath = currentState['execution_output_path']?.toString();
              
              // Extract type information for endpoint construction (update if changed)
              final inputType = currentState['input_type']?.toString().toUpperCase();
              final typeSavepoint = currentState['type_savepoint'];
              final outputType = (typeSavepoint is List && typeSavepoint.isNotEmpty)
                  ? typeSavepoint.last.toString().toUpperCase()
                  : null;
              
              _inputType = inputType;
              _outputType = outputType;
            }
          });
        }
      });
    });

    // Listen to path discovery - single source of truth for animation
    widget.streamingService!.pathDiscovery.listen((paths) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {
            _allPaths = paths;
            if (paths.isNotEmpty) {
              _currentPaths = [];
              _animationMode = 'find_path';
              _currentPathIndex = 0;
              _populateCompleted = false;
              _reduceStarted = false;
            }
          });
          
          // Drive propagation animation directly
          if (paths.isNotEmpty) {
            final propagationState = _propagationKey.currentState;
            debugPrint('📊 EXECUTION PANEL: Calling startPathAnimation - state exists: ${propagationState != null}');
            if (propagationState != null) {
              (propagationState as dynamic).startPathAnimation(paths);
            }
          }
        } else {
          debugPrint('❌ EXECUTION PANEL: Widget not mounted!');
        }
      });
    });

    // Listen to chosen path - transition to reduce mode (execution details shown AFTER reduce completes)
    widget.streamingService!.chosenPath.listen((path) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {
            _chosenPath = path;
            
            // Only trigger reduce animation if path has actual tools (not just endpoints)
            if (path.length > 2 && _populateCompleted) {
              _animationMode = 'reduce';
              _reduceStarted = true;
              _currentPathIndex = 0;
            }
          });
          
          if (path.length > 2) {
            final propagationState = _propagationKey.currentState;
            if (propagationState != null) {
              (propagationState as dynamic).setChosenPath(path);
            }
          }
        }
      });
    });
    
    // Listen to executor step events for node highlighting
    widget.streamingService!.executorSteps.listen((stepData) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          setState(() {
            if (stepData.status == 'start') {
              _currentExecutingTool = stepData.toolName;
              debugPrint('🔧 EXECUTION: Tool started: $_currentExecutingTool');
              
              // Auto-select the executing tool ONLY if user hasn't manually selected a different node
              if (_selectedToolName == null) {
                _selectedToolName = stepData.toolName;
                _selectedStepIndex = stepData.stepIndex;
                debugPrint('🎯 EXECUTION: Auto-selected tool: $_selectedToolName');
              } else {
                debugPrint('🎯 EXECUTION: Keeping manual selection: $_selectedToolName (executing: $_currentExecutingTool in background)');
              }
            } else if (stepData.status == 'end') {
              debugPrint('🔧 EXECUTION: Tool ended: ${stepData.toolName}');
              _currentExecutingTool = null;
              
              // If the ended tool was the selected one, clear selection
              // (This allows the next tool to auto-select)
              if (_selectedToolName == stepData.toolName) {
                _selectedToolName = null;
                _selectedStepIndex = null;
                debugPrint('🎯 EXECUTION: Cleared selection after tool completed');
              }
            }
          });
        }
      });
    });
  }
  
  /// Check if we have valid graph data to display
  bool get hasGraph {
    return (_allPaths.isNotEmpty) ||
           (_chosenPath != null && _chosenPath!.isNotEmpty) ||
           (widget.streamingService != null); // Always show graph when streaming is active
  }
  
  /// Update animation state callbacks (like NextJS dispatch actions)
  void _onAnimationModeChanged(String mode) {
    setState(() {
      _animationMode = mode;
    });
  }
  
  void _onPathIndexChanged(int index) {
    setState(() {
      _currentPathIndex = index;
    });
  }
  
  void _onPopulateCompleted(bool completed) {
    setState(() {
      _populateCompleted = completed;
    });
  }
  
  void _onReduceStarted(bool started) {
    setState(() {
      _reduceStarted = started;
    });
  }
  
  void _onReduceCompleted() {
    setState(() {
      // Show execution details AFTER reduce animation completes
      _showExecutionDetails = true;
    });
    debugPrint('✅ EXECUTION PANEL: Reduce completed - showing execution details');
  }
  
  void _onCurrentPathAdded(List<String> path) {
    setState(() {
      if (!_currentPaths.any((p) => 
          p.length == path.length && 
          p.asMap().entries.every((entry) => entry.value == path[entry.key]))) {
        _currentPaths.add(List<String>.from(path));
        debugPrint('📋 Added path ${_currentPaths.length}: ${path.join(' -> ')}');
      }
    });
  }
  
  void _onCurrentPathRemoved(List<String> path) {
    setState(() {
      _currentPaths.removeWhere((p) => 
          p.length == path.length && 
          p.asMap().entries.every((entry) => entry.value == path[entry.key]));
      debugPrint('🗑️  Removed path: ${path.join(' -> ')}');
    });
  }
  
  void _onResetCurrentPaths() {
    setState(() {
      _currentPaths.clear();
    });
  }

  /// Start populate animation (revealing paths one by one)
  void startPopulateAnimation() {
    setState(() {
      // Reset to find_path mode
      _currentPaths = [];
      _animationMode = 'find_path';
      _currentPathIndex = 0;
      _populateCompleted = false;
      _reduceStarted = false;
    });
    
    // Call restart on propagation component
    final propagationWidget = _propagationKey.currentWidget as Propagation?;
    if (propagationWidget != null) {
      final propagationState = _propagationKey.currentState;
      if (propagationState != null) {
        (propagationState as dynamic).restart();
        debugPrint('✅ EXECUTION PANEL: Propagation animation restarted');
      }
    }
    
    // Call restart on pipeline component  
    final pipelineWidget = _pipelineKey.currentWidget as Pipeline?;
    if (pipelineWidget != null) {
      final pipelineState = _pipelineKey.currentState;
      if (pipelineState != null) {
        (pipelineState as dynamic).restart();
        debugPrint('✅ EXECUTION PANEL: Pipeline animation restarted');
      }
    }
  }
  
  /// Start reduce animation (eliminating non-chosen paths)
  void startReduceAnimation() {
    if (_chosenPath == null || _chosenPath!.isEmpty) {
      debugPrint('❌ Cannot start reduce: no chosen path');
      return;
    }
    
    setState(() {
      // Set to reduce mode
      _animationMode = 'reduce';
      _currentPathIndex = 0;
      _populateCompleted = true;
      _reduceStarted = true;
    });
    
    // Start reduce animation in Propagation
    final propagationState = _propagationKey.currentState;
    if (propagationState != null) {
      (propagationState as dynamic).setChosenPath(_chosenPath!);
    }
  }

  /// Restart animations in both propagation and pipeline components
  void restartAnimations() {
    startPopulateAnimation();
  }
  
  /// Handle tool selection from propagation graph
  void _handleToolSelected(String toolName, int stepIndex) {
    setState(() {
      _selectedToolName = toolName;
      _selectedStepIndex = stepIndex;
    });
    debugPrint('🎯 EXECUTION: Manual selection: $toolName (step $stepIndex)');
  }

  @override
  Widget build(BuildContext context) {
    // Build the visualization panel
    final visualizationPanel = Container(
      margin: EdgeInsets.fromLTRB(16, 16, 16, _showExecutionDetails ? 8 : 16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE2E8F0)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 10,
            spreadRadius: 0,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: hasGraph ? _buildVisualizationContent() : _buildWaitingState(),
      ),
    );
    
    return Container(
      color: const Color(0xFFF8FAFC),
      child: _showExecutionDetails
          ? ResizablePanels(
              isVertical: true, // Top/bottom split
              initialRatio: 0.6, // Propagation takes 60% initially
              minFirstPanelRatio: 0.4, // Propagation minimum 40%
              maxFirstPanelRatio: 0.8, // Propagation maximum 80%
              dividerThickness: 6.0,
              dividerColor: const Color(0xFFE2E8F0),
              dividerHoverColor: Colors.grey.shade300,
              firstPanel: visualizationPanel,
              secondPanel: Container(
          margin: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          child: Row(
            children: [
              // Left side: Column with Code Block on top and Console on bottom
              Expanded(
                flex: 1,
                child: Container(
                  margin: const EdgeInsets.only(right: 8),
                  child: Column(
                    children: [
                      // Code Block (top half)
                      Expanded(
                        flex: 1,
                        child: Container(
                          margin: const EdgeInsets.only(bottom: 4),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: const Color(0xFFE2E8F0)),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.05),
                                blurRadius: 10,
                                spreadRadius: 0,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child:                             CodeBlock(
                              streamingService: widget.streamingService,
                              currentToolName: _selectedToolName,
                              currentStepIndex: _selectedStepIndex,
                              chosenPath: widget.staticChosenPath ?? _chosenPath,
                              executionOutputPath: _executionOutputPath,
                            ),
                          ),
                        ),
                      ),
                      
                      // Console (bottom half)
                      Expanded(
                        flex: 1,
                        child: Container(
                          margin: const EdgeInsets.only(top: 4),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: const Color(0xFFE2E8F0)),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.05),
                                blurRadius: 10,
                                spreadRadius: 0,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child:                             Console(
                              streamingService: widget.streamingService,
                              currentStepIndex: _selectedStepIndex,
                              currentToolName: _selectedToolName,
                              chosenPath: widget.staticChosenPath ?? _chosenPath,
                              executionOutputPath: _executionOutputPath,
                              currentConversationId: widget.chatId,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              
              // Right side: Preview (full height)
              Expanded(
                flex: 1,
                child: Container(
                  margin: const EdgeInsets.only(left: 8),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: const Color(0xFFE2E8F0)),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.05),
                        blurRadius: 10,
                        spreadRadius: 0,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: Preview(
                      streamingService: widget.streamingService,
                      executionOutputPath: _executionOutputPath,
                      currentConversationId: widget.chatId,
                      currentStepIndex: _selectedStepIndex,
                      currentToolName: _selectedToolName,
                      chosenPath: widget.staticChosenPath ?? _chosenPath,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
              )
          : visualizationPanel,
    );
  }
  
  /// Build the main visualization content with graph and pipeline
  Widget _buildVisualizationContent() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          // Header with controls
          _buildVisualizationHeader(),
          const SizedBox(height: 16),
          // Main visualization area
          Expanded(
            child: Row(
              children: [
                // Left side: Propagation graph (takes most of the space)
                Expanded(
                  flex: 2,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildSectionHeader('Propagation'),
                      const SizedBox(height: 8),
                      Expanded(
                        child: Propagation(
                          key: _propagationKey,
                          workflowState: _currentWorkflow,
                          allPaths: _allPaths,
                          chosenPath: _chosenPath,
                          executingNodeId: _selectedToolName, // Highlight the displayed node
                          streamingService: widget.streamingService,
                          inputType: _inputType,
                          outputType: _outputType,
                          // Animation state callbacks (like NextJS dispatch)
                          onAnimationModeChanged: _onAnimationModeChanged,
                          onPathIndexChanged: _onPathIndexChanged,
                          onPopulateCompleted: _onPopulateCompleted,
                          onReduceStarted: _onReduceStarted,
                          onReduceCompleted: _onReduceCompleted,
                          onCurrentPathAdded: _onCurrentPathAdded,
                          onCurrentPathRemoved: _onCurrentPathRemoved,
                          onResetCurrentPaths: _onResetCurrentPaths,
                          onToolSelected: _handleToolSelected,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 16),
                // Right side: Pipeline view
                Expanded(
                  flex: 1,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildSectionHeader('Pipeline'),
                      const SizedBox(height: 8),
                      Expanded(
                        child: Pipeline(
                          key: _pipelineKey,
                          workflowState: _currentWorkflow,
                          allPaths: _allPaths,
                          currentPaths: _currentPaths, // Share current paths like NextJS
                          chosenPath: _chosenPath,
                          executingNodeId: _executingNodeId,
                          animationMode: _animationMode, // Share animation mode
                          currentPathIndex: _currentPathIndex, // Share current index
                          populateCompleted: _populateCompleted,
                          reduceStarted: _reduceStarted,
                          streamingService: widget.streamingService,
                          onRestart: restartAnimations,
                          inputType: _inputType,
                          outputType: _outputType,
                          onStepTapped: () {
                            // TODO: Handle step selection
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Build header with visualization controls
  Widget _buildVisualizationHeader() {
    return Row(
      children: [
        const Text(
          'Execution Visualization',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Color(0xFF111827),
          ),
        ),
        const Spacer(),
        // Animation control buttons
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Populate button
            ElevatedButton.icon(
              onPressed: startPopulateAnimation,
              icon: const Icon(Icons.add_road, size: 16),
              label: const Text('Populate'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFF0FDF4),
                foregroundColor: const Color(0xFF22C55E),
                elevation: 0,
                side: const BorderSide(color: Color(0xFFA7F3D0)),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                textStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
              ),
            ),
            const SizedBox(width: 8),
            // Reduce button
            ElevatedButton.icon(
              onPressed: _chosenPath != null && _chosenPath!.isNotEmpty 
                ? startReduceAnimation 
                : null,
              icon: const Icon(Icons.filter_list, size: 16),
              label: const Text('Reduce'),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFFEF2F2),
                foregroundColor: const Color(0xFFEF4444),
                elevation: 0,
                side: const BorderSide(color: Color(0xFFFECACA)),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                textStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                disabledBackgroundColor: const Color(0xFFF9FAFB),
                disabledForegroundColor: const Color(0xFF9CA3AF),
              ),
            ),
            // Close button (only show if onClose callback is provided)
            if (widget.onClose != null) ...[
              const SizedBox(width: 8),
              IconButton(
                icon: const Icon(Icons.close, size: 18),
                onPressed: widget.onClose,
                tooltip: 'Collapse Execution Panel',
                color: Colors.grey.shade600,
                padding: const EdgeInsets.all(8),
                constraints: const BoxConstraints(
                  minWidth: 32,
                  minHeight: 32,
                ),
                iconSize: 18,
                splashRadius: 20,
              ),
            ],
          ],
        ),
      ],
    );
  }

  /// Build waiting state when no graph data is available
  Widget _buildWaitingState() {
    return const Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.hub_outlined,
            color: Color(0xFF6B7280),
            size: 64,
          ),
          SizedBox(height: 16),
          Text(
            'No path data yet',
            style: TextStyle(
              color: Color(0xFF374151),
              fontSize: 16,
              fontWeight: FontWeight.w500,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Waiting for find_path...',
            style: TextStyle(
              color: Color(0xFF6B7280),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  /// Build section header with title
  Widget _buildSectionHeader(String title) {
    return Text(
      title,
      style: const TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w600,
        color: Color(0xFF111827),
      ),
    );
  }
}
