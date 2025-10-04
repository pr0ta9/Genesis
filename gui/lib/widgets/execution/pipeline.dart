import 'package:flutter/material.dart';
import 'package:gui/data/services/streaming_service.dart';

/// Represents a step in the execution pipeline
class PipelineStep {
  final String id;
  final String title;
  final bool isEndpoint;
  final bool isChosen;
  final bool isExecuting;
  final bool isBeingAdded;
  final bool isBeingEliminated;
  final Color? color;

  const PipelineStep({
    required this.id,
    required this.title,
    this.isEndpoint = false,
    this.isChosen = false,
    this.isExecuting = false,
    this.isBeingAdded = false,
    this.isBeingEliminated = false,
    this.color,
  });

  PipelineStep copyWith({
    String? id,
    String? title,
    bool? isEndpoint,
    bool? isChosen,
    bool? isExecuting,
    bool? isBeingAdded,
    bool? isBeingEliminated,
    Color? color,
  }) {
    return PipelineStep(
      id: id ?? this.id,
      title: title ?? this.title,
      isEndpoint: isEndpoint ?? this.isEndpoint,
      isChosen: isChosen ?? this.isChosen,
      isExecuting: isExecuting ?? this.isExecuting,
      isBeingAdded: isBeingAdded ?? this.isBeingAdded,
      isBeingEliminated: isBeingEliminated ?? this.isBeingEliminated,
      color: color ?? this.color,
    );
  }
}

/// Represents a complete execution path in the pipeline
class ExecutionPath {
  final List<PipelineStep> steps;
  final bool isChosen;
  final bool isBeingAdded;
  final bool isBeingEliminated;
  final int pathIndex;

  const ExecutionPath({
    required this.steps,
    this.isChosen = false,
    this.isBeingAdded = false,
    this.isBeingEliminated = false,
    required this.pathIndex,
  });
}

/// Pipeline widget that displays execution paths with animated steps
class Pipeline extends StatefulWidget {
  final WorkflowState? workflowState;
  final List<List<String>>? allPaths;  // Pure tool lists, no endpoints
  final List<List<String>>? currentPaths; // Shared UI-ephemeral paths like NextJS
  final List<String>? chosenPath;  // Pure tool list, no endpoints
  final String? executingNodeId;
  final String animationMode; // Shared animation mode
  final int currentPathIndex; // Shared current index
  final bool populateCompleted;
  final bool reduceStarted;
  final VoidCallback? onStepTapped;
  final StreamingService? streamingService;
  final VoidCallback? onRestart;
  
  // Workflow type information (for endpoint construction in visualization)
  final String? inputType;   // e.g., "AUDIO", "IMAGE", "TEXT"
  final String? outputType;  // e.g., "AUDIO", "IMAGE", "TEXT"

  const Pipeline({
    Key? key,
    this.workflowState,
    this.allPaths,
    this.currentPaths,
    this.chosenPath,
    this.executingNodeId,
    this.animationMode = 'find_path',
    this.currentPathIndex = 0,
    this.populateCompleted = false,
    this.reduceStarted = false,
    this.onStepTapped,
    this.streamingService,
    this.onRestart,
    this.inputType,
    this.outputType,
  }) : super(key: key);

  @override
  State<Pipeline> createState() => _PipelineState();
}

class _PipelineState extends State<Pipeline> with TickerProviderStateMixin {
  late AnimationController _pathAnimationController;
  
  late Animation<double> _pathAnimation;
  
  List<ExecutionPath> _visiblePaths = [];
  
  // Scroll controller for auto-scroll to bottom
  final ScrollController _scrollController = ScrollController();
  
  // Colors
  static const Color endpointColor = Color(0xFFCBDCEB);
  static const Color chosenPathColor = Color(0xFF3B82F6);

  @override
  void initState() {
    super.initState();
    
    // Debug cleaned up - pipeline initialized
    
    _pathAnimationController = AnimationController(
      duration: const Duration(milliseconds: 100), // Faster: 200ms -> 100ms
      vsync: this,
    );
    
    _pathAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _pathAnimationController,
      curve: Curves.easeInOut,
    ));
    
    _updatePaths();
    _pathAnimationController.forward();
  }

  /// Helper: Add endpoints to a path for visualization
  /// Paths are stored as pure tool lists, endpoints are added only for display
  List<String> _addEndpoints(List<String> toolPath) {
    if (widget.inputType == null || widget.outputType == null) {
      // Fallback if type info not available (shouldn't happen in normal flow)
      return ['IN', ...toolPath, 'OUT'];
    }
    
    final inputEndpoint = '${widget.inputType}_IN';
    final outputEndpoint = '${widget.outputType}_OUT';
    return [inputEndpoint, ...toolPath, outputEndpoint];
  }

  /// Helper: Add endpoints to multiple paths for visualization
  List<List<String>> _addEndpointsToAll(List<List<String>> toolPaths) {
    return toolPaths.map((path) => _addEndpoints(path)).toList();
  }

  @override
  void didUpdateWidget(Pipeline oldWidget) {
    super.didUpdateWidget(oldWidget);
    
    // Update when shared animation state changes (like NextJS)
    if (widget.allPaths != oldWidget.allPaths ||
        widget.currentPaths != oldWidget.currentPaths ||
        widget.chosenPath != oldWidget.chosenPath ||
        widget.executingNodeId != oldWidget.executingNodeId ||
        widget.animationMode != oldWidget.animationMode ||
        widget.currentPathIndex != oldWidget.currentPathIndex) {
      // Debug: Pipeline state change
      
      _updatePaths();
      
      // Auto-scroll logic - more aggressive approach
      final bool pathCountIncreased = _visiblePaths.length > 0 && 
                                      ((widget.currentPaths?.length ?? 0) > (oldWidget.currentPaths?.length ?? 0) ||
                                       (widget.allPaths?.length ?? 0) > (oldWidget.allPaths?.length ?? 0));
      final bool isInFindPathMode = widget.animationMode == 'find_path';
      final bool pathIndexProgressed = widget.currentPathIndex > oldWidget.currentPathIndex;
      
      // Auto-scroll when paths are being added/discovered
      if ((pathCountIncreased || pathIndexProgressed) && isInFindPathMode && _visiblePaths.length > 1) {
        _scrollToBottom();
      }
    }
  }

  @override
  void dispose() {
    _pathAnimationController.dispose();
    _scrollController.dispose();
    super.dispose();
  }
  
  /// Auto-scroll to bottom to show newest paths
  void _scrollToBottom() {
    if (!_scrollController.hasClients) return;
    
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }
  
  /// Force scroll to bottom (can be called externally)
  void scrollToBottom() {
    _scrollToBottom();
  }
  
  /// Restart the pipeline animation
  void restart() {
    _pathAnimationController.reset();
    _updatePaths();
    _pathAnimationController.forward();
    
    // Scroll to top on restart
    if (_scrollController.hasClients) {
      _scrollController.animateTo(0.0, duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
    }
  }

  /// Update the visible paths based on shared animation state (like NextJS)
  void _updatePaths() {
    _visiblePaths.clear();
    
    // Pipeline updating paths (mode: ${widget.animationMode})
    
    // Simple logic: prioritize currentPaths (managed by ExecutionPanel)
    List<List<String>> rawPaths = [];
    
    if (widget.currentPaths != null && widget.currentPaths!.isNotEmpty) {
      rawPaths = widget.currentPaths!;
    } else if (widget.allPaths != null && widget.allPaths!.isNotEmpty) {
      rawPaths = widget.allPaths!;
    }
    
    if (rawPaths.isEmpty) {
      setState(() {});
      return;
    }
    
    // Add endpoints for visualization
    final pathsToDisplay = _addEndpointsToAll(rawPaths);
    
    final hasChosenPath = widget.chosenPath != null && widget.chosenPath!.isNotEmpty;
    
    for (int pathIndex = 0; pathIndex < pathsToDisplay.length; pathIndex++) {
      final path = pathsToDisplay[pathIndex];
      final isChosen = hasChosenPath && widget.animationMode == 'chosen_path';
      
      // Determine animation states based on mode and index (like NextJS)
      final globalIndex = widget.allPaths?.indexWhere((p) => 
        p.length == path.length && 
        p.asMap().entries.every((entry) => entry.value == path[entry.key])
      ) ?? pathIndex;
      
      final isBeingAdded = widget.animationMode == 'find_path' && 
                           globalIndex == widget.currentPathIndex;
      final isBeingEliminated = widget.animationMode == 'reduce' && 
                                widget.reduceStarted && 
                                globalIndex == widget.currentPathIndex;
      
      
      final steps = path.map((stepId) {
        final isEndpoint = _isEndpointNode(stepId);
        final isExecuting = widget.executingNodeId == stepId && !isEndpoint;
        
        return PipelineStep(
          id: stepId,
          title: stepId,
          isEndpoint: isEndpoint,
          isChosen: isChosen,
          isExecuting: isExecuting,
          isBeingAdded: isBeingAdded,
          isBeingEliminated: isBeingEliminated,
          color: _getStepColor(stepId, isChosen),
        );
      }).toList();
      
      _visiblePaths.add(ExecutionPath(
        steps: steps,
        isChosen: isChosen,
        isBeingAdded: isBeingAdded,
        isBeingEliminated: isBeingEliminated,
        pathIndex: globalIndex,
      ));
    }
    
    setState(() {});
    
    // Auto-scroll during animation
    if (widget.animationMode == 'find_path' && !widget.populateCompleted && pathsToDisplay.length > 0) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToBottom();
      });
    }
  }

  /// Check if a node is an endpoint
  bool _isEndpointNode(String nodeId) {
    return nodeId.contains('_IN') || nodeId.contains('_OUT');
  }

  /// Get count of intermediate steps (excluding IN/OUT endpoints)
  int _getIntermediateStepCount(ExecutionPath path) {
    return path.steps.where((step) => !step.isEndpoint).length;
  }

  /// Get color for a step based on its state (matching propagation widget colors)
  Color _getStepColor(String stepId, bool isChosen) {
    if (_isEndpointNode(stepId)) return endpointColor;
    
    // Use same seed-based color generation as propagation widget
    final hash = stepId.hashCode.abs();
    final hue = (hash % 360).toDouble();
    const saturation = 0.65; // 65% saturation for vibrant but not overwhelming colors
    const lightness = 0.75;  // 75% lightness for good contrast with text
    
    final color = HSLColor.fromAHSL(1.0, hue, saturation, lightness).toColor();
    return color;
  }

  /// Get title text based on current state (like NextJS)
  String _getTitleText() {
    final hasChosenPath = widget.chosenPath != null && widget.chosenPath!.isNotEmpty;
    final isSelectedView = hasChosenPath && 
                          _visiblePaths.length == 1 && 
                          widget.animationMode == 'chosen_path';
    return isSelectedView ? "Selected path" : "Available paths";
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          _buildHeader(),
          // Paths list
          Expanded(
            child: _buildPathsList(),
          ),
        ],
      ),
    );
  }

  /// Build the header section
  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: const BoxDecoration(
        border: Border(
          bottom: BorderSide(color: Color(0xFFE2E8F0)),
        ),
      ),
      child: Row(
        children: [
          Text(
            _getTitleText(),
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: Color(0xFF111827),
            ),
          ),
        ],
      ),
    );
  }

  /// Build the paths list
  Widget _buildPathsList() {
    if (_visiblePaths.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Text(
            'Waiting for available paths...',
            style: TextStyle(
              color: Color(0xFF64748B),
              fontSize: 14,
            ),
          ),
        ),
      );
    }

    return AnimatedBuilder(
      animation: _pathAnimation,
      builder: (context, child) {
        return ListView.builder(
          controller: _scrollController, // Enable auto-scroll
          padding: const EdgeInsets.all(16),
          itemCount: _visiblePaths.length,
          itemBuilder: (context, index) {
            final path = _visiblePaths[index];
            return _buildPathCard(path, index);
          },
        );
      },
    );
  }

  /// Build a single path card
  Widget _buildPathCard(ExecutionPath path, int index) {
    return AnimatedContainer(
      duration: Duration(milliseconds: 100 + index * 25), // Faster: 200ms->100ms, 50ms->25ms stagger
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: path.isBeingEliminated
            ? const Color(0xFFFEE2E2)
            : path.isBeingAdded
                ? const Color(0xFFF0FDF4)
                : path.isChosen
                    ? const Color(0xFFEFF6FF)
                    : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: path.isBeingEliminated
              ? const Color(0xFFFCA5A5)
              : path.isBeingAdded
                  ? const Color(0xFFA7F3D0)
                  : path.isChosen
                      ? const Color(0xFFBFDBFE)
                      : const Color(0xFFE5E7EB),
        ),
        boxShadow: path.isChosen
            ? [
                BoxShadow(
                  color: Colors.blue.withOpacity(0.1),
                  blurRadius: 4,
                  offset: const Offset(0, 2),
                ),
              ]
            : null,
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Path header
            _buildPathHeader(path, index),
            const SizedBox(height: 12),
            // Path steps
            _buildPathSteps(path),
          ],
        ),
      ),
    );
  }

  /// Build path header with title and metadata
  Widget _buildPathHeader(ExecutionPath path, int index) {
    return Row(
      children: [
        // Path index badge
        Container(
          width: 24,
          height: 24,
          decoration: BoxDecoration(
            color: path.isChosen ? chosenPathColor : const Color(0xFF6B7280),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Center(
            child: Text(
              '${index + 1}',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
        const SizedBox(width: 8),
        // Path title
        Text(
          'Path ${path.pathIndex + 1}',
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: Color(0xFF111827),
          ),
        ),
        const SizedBox(width: 8),
        // Step count badge
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
          decoration: BoxDecoration(
            color: const Color(0xFFF3F4F6),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(
            '${_getIntermediateStepCount(path)} step${_getIntermediateStepCount(path) == 1 ? '' : 's'}',
            style: const TextStyle(
              fontSize: 11,
              color: Color(0xFF6B7280),
            ),
          ),
        ),
      ],
    );
  }

  /// Build the visual representation of path steps
  Widget _buildPathSteps(ExecutionPath path) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (int i = 0; i < path.steps.length; i++) ...[
          _buildStepChip(path.steps[i], path),
          if (i < path.steps.length - 1) _buildArrow(path),
        ],
      ],
    );
  }

  /// Build a single step chip
  Widget _buildStepChip(PipelineStep step, ExecutionPath path) {
    final isExecuting = step.isExecuting;
    
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      padding: EdgeInsets.symmetric(
        horizontal: isExecuting ? 14 : 12,
        vertical: isExecuting ? 10 : 8,
      ),
      decoration: BoxDecoration(
        gradient: _getStepGradient(step, path),
        borderRadius: BorderRadius.circular(8),
        boxShadow: isExecuting
            ? [
                BoxShadow(
                  color: Colors.indigo.withOpacity(0.35),
                  blurRadius: 4,
                  offset: const Offset(0, 0),
                ),
              ]
            : null,
      ),
      child: GestureDetector(
        onTap: widget.onStepTapped,
        child: Text(
          step.title,
          style: TextStyle(
            fontSize: 12,
            fontWeight: isExecuting ? FontWeight.w600 : FontWeight.w500,
            color: isExecuting ? const Color(0xFF312E81) : const Color(0xFF374151),
          ),
        ),
      ),
    );
  }

  /// Get gradient for step chip
  LinearGradient _getStepGradient(PipelineStep step, ExecutionPath path) {
    if (step.isEndpoint) {
      return const LinearGradient(
        colors: [endpointColor, endpointColor],
      );
    }
    
    if (path.isBeingEliminated) {
      return const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFFFECACA), Color(0xFFF87171)],
      );
    }
    
    if (path.isBeingAdded) {
      return const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFFDCFCE7), Color(0xFF86EFAC)],
      );
    }
    
    if (path.isChosen) {
      final baseColor = step.color ?? chosenPathColor;
      return LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          baseColor.withOpacity(0.8),
          baseColor.withOpacity(0.6),
        ],
      );
    }
    
    // Use the step's custom color for normal paths too
    final baseColor = step.color ?? const Color(0xFFF8FAFC);
    return LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [
        baseColor,
        baseColor.withOpacity(0.85), // Slightly darker for gradient effect
      ],
    );
  }

  /// Build arrow between steps
  Widget _buildArrow(ExecutionPath path) {
    return Icon(
      Icons.arrow_forward,
      size: 16,
      color: path.isBeingEliminated
          ? const Color(0xFFEF4444)
          : path.isBeingAdded
              ? const Color(0xFF22C55E)
              : path.isChosen
                  ? const Color(0xFF3B82F6)
                  : const Color(0xFF9CA3AF),
    );
  }

}
