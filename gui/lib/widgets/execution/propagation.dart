import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:gui/data/services/streaming_service.dart';

/// Represents a node in the workflow graph
class WorkflowNode {
  final String id;
  final String title;
  final Offset position;
  final Color color;
  final bool isEndpoint;
  final bool isActive;
  final bool isExecuting;

  const WorkflowNode({
    required this.id,
    required this.title,
    required this.position,
    required this.color,
    this.isEndpoint = false,
    this.isActive = false,
    this.isExecuting = false,
  });

  WorkflowNode copyWith({
    String? id,
    String? title,
    Offset? position,
    Color? color,
    bool? isEndpoint,
    bool? isActive,
    bool? isExecuting,
  }) {
    return WorkflowNode(
      id: id ?? this.id,
      title: title ?? this.title,
      position: position ?? this.position,
      color: color ?? this.color,
      isEndpoint: isEndpoint ?? this.isEndpoint,
      isActive: isActive ?? this.isActive,
      isExecuting: isExecuting ?? this.isExecuting,
    );
  }
}

/// Represents an edge connecting two nodes
class WorkflowEdge {
  final String id;
  final String fromNodeId;
  final String toNodeId;
  final bool isVisible;
  final bool isHighlighted;
  final bool isAnimating;

  const WorkflowEdge({
    required this.id,
    required this.fromNodeId,
    required this.toNodeId,
    this.isVisible = false,
    this.isHighlighted = false,
    this.isAnimating = false,
  });

  WorkflowEdge copyWith({
    String? id,
    String? fromNodeId,
    String? toNodeId,
    bool? isVisible,
    bool? isHighlighted,
    bool? isAnimating,
  }) {
    return WorkflowEdge(
      id: id ?? this.id,
      fromNodeId: fromNodeId ?? this.fromNodeId,
      toNodeId: toNodeId ?? this.toNodeId,
      isVisible: isVisible ?? this.isVisible,
      isHighlighted: isHighlighted ?? this.isHighlighted,
      isAnimating: isAnimating ?? this.isAnimating,
    );
  }
}

/// Animation modes for the propagation graph
enum PropagationAnimationMode {
  findPath,    // Discovering and revealing paths
  reduce,      // Eliminating paths to show chosen path  
  chosenPath,  // Static display of selected path
}

/// Main Propagation widget that visualizes workflow execution as an animated graph
class Propagation extends StatefulWidget {
  final WorkflowState? workflowState;
  final List<List<String>>? allPaths;        // Pure tool lists, no endpoints
  final List<String>? chosenPath;            // Pure tool list, no endpoints
  final String? executingNodeId;
  final StreamingService? streamingService;
  
  // Workflow type information (for endpoint construction in visualization)
  final String? inputType;   // e.g., "AUDIO", "IMAGE", "TEXT"
  final String? outputType;  // e.g., "AUDIO", "IMAGE", "TEXT"
  
  // Animation state callbacks (like NextJS dispatch actions)
  final Function(String)? onAnimationModeChanged;
  final Function(int)? onPathIndexChanged;
  final Function(bool)? onPopulateCompleted;
  final Function(bool)? onReduceStarted;
  final VoidCallback? onReduceCompleted;
  final Function(List<String>)? onCurrentPathAdded;
  final Function(List<String>)? onCurrentPathRemoved;
  final VoidCallback? onResetCurrentPaths;
  final Function(String toolName, int stepIndex)? onToolSelected;

  const Propagation({
    Key? key,
    this.workflowState,
    this.allPaths,
    this.chosenPath,
    this.executingNodeId,
    this.streamingService,
    this.inputType,
    this.outputType,
    this.onAnimationModeChanged,
    this.onPathIndexChanged,
    this.onPopulateCompleted,
    this.onReduceStarted,
    this.onReduceCompleted,
    this.onCurrentPathAdded,
    this.onCurrentPathRemoved,
    this.onResetCurrentPaths,
    this.onToolSelected,
  }) : super(key: key);

  @override
  State<Propagation> createState() => _PropagationState();
}

class _PropagationState extends State<Propagation> with TickerProviderStateMixin {
  // Animation controllers
  late AnimationController _pathRevealController;
  late AnimationController _nodeScaleController;
  late AnimationController _edgeAnimationController;
  
  // Animation values
  late Animation<double> _pathRevealAnimation;
  late Animation<double> _nodeScaleAnimation;
  late Animation<double> _edgeAnimation;

  // Graph state
  Map<String, WorkflowNode> _nodes = {};
  List<WorkflowEdge> _edges = [];
  PropagationAnimationMode _animationMode = PropagationAnimationMode.findPath;
  
  // Animation state
  bool _isPlaying = true;
  int _currentPathIndex = 0;
  Set<String> _revealedNodes = {};
  Set<String> _revealedEdges = {};
  Set<String> _highlightedEdges = {};
  
  // Stream subscriptions
  StreamSubscription<List<List<String>>>? _pathDiscoverySubscription;
  StreamSubscription<List<String>>? _chosenPathSubscription;
  
  // Current paths data
  List<List<String>> _discoveredPaths = []; // Visual paths (with endpoints)
  List<List<String>> _rawDiscoveredPaths = []; // Pure tool lists (no endpoints)
  List<String>? _currentChosenPath; // Visual path (with endpoints)
  List<String>? _rawChosenPath; // Pure tool list (no endpoints)
  
  // Mouse interaction state
  bool _isHoveringClickableNode = false;
  
  // Layout constants
  static const double nodeWidth = 88.0;
  static const double nodeHeight = 34.0;
  static const double fontSize = 14.0;
  static const double edgeStrokeWidth = 2.0;
  static const double highlightedEdgeStrokeWidth = 3.0;
  static const double minNodeDistance = 30.0; // Minimum distance between node centers - reduced for better spacing
  
  // Colors
  static const Color endpointColor = Color(0xFFCBDCEB);
  static const Color activeEdgeColor = Color(0xFF6366F1);
  static const Color normalEdgeColor = Color(0xFFE2E8F0);

  @override
  void initState() {
    super.initState();
    
    debugPrint('🚀 PROPAGATION: initState called');
    
    // Initialize animation controllers
    _pathRevealController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );
    
    _nodeScaleController = AnimationController(
      duration: const Duration(milliseconds: 100),
      vsync: this,
    );
    
    _edgeAnimationController = AnimationController(
      duration: const Duration(milliseconds: 100),
      vsync: this,
    );

    // Initialize animations
    _pathRevealAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _pathRevealController,
      curve: Curves.easeInOut,
    ));
    
    _nodeScaleAnimation = Tween<double>(
      begin: 1.0,
      end: 1.15,
    ).animate(CurvedAnimation(
      parent: _nodeScaleController,
      curve: Curves.elasticOut,
    ));
    
    _edgeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _edgeAnimationController,
      curve: Curves.easeInOut,
    ));

    // Initialize graph data
    _initializeGraph();
    
  // NO streaming subscriptions - Propagation is now a pure display component
  // Animation is driven by execution panel via callbacks
  
  // For static data, show full graph immediately (no animation needed)
  if (widget.allPaths != null && widget.allPaths!.isNotEmpty) {
    debugPrint('🎬 PROPAGATION: Static data - showing full graph immediately');
    _showFullGraphForStaticData();
  } else {
    debugPrint('⏳ PROPAGATION: No initial paths - waiting for execution panel to drive animation');
  }
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
  void didUpdateWidget(Propagation oldWidget) {
    super.didUpdateWidget(oldWidget);
    
    
    // Update graph ONLY when paths actually change (not on every workflow state change)
    if (widget.allPaths != oldWidget.allPaths ||
        widget.chosenPath != oldWidget.chosenPath) {
      _updateGraph();
      
      // For static data changes, show full graph immediately (no animation needed)
      if (widget.streamingService == null && 
          widget.allPaths != null && 
          widget.allPaths!.isNotEmpty &&
          (oldWidget.allPaths != widget.allPaths)) {
        debugPrint('🎨 PROPAGATION: Static data updated - showing full graph');
        Future.microtask(() => _showFullGraphForStaticData());
      }
    }
    
    // Handle mode transitions (only for streaming, not static data)
    if (widget.streamingService != null &&
        widget.chosenPath != null && widget.chosenPath!.isNotEmpty && 
        _animationMode == PropagationAnimationMode.findPath) {
      _transitionToReduceMode();
    }
  }

  @override
  void dispose() {
    _pathRevealController.dispose();
    _nodeScaleController.dispose();
    _edgeAnimationController.dispose();
    _pathDiscoverySubscription?.cancel();
    _chosenPathSubscription?.cancel();
    super.dispose();
  }

  /// Start path animation from execution panel control
  void startPathAnimation(List<List<String>> paths) {
    if (paths.isEmpty) return;
    
    // Store both pure and visual paths
    _rawDiscoveredPaths = paths;
    final visualPaths = _addEndpointsToAll(paths);
    
    setState(() {
      _discoveredPaths = visualPaths;
      _currentPathIndex = 0;
      _revealedNodes.clear();
      _revealedNodes.addAll(_getEndpointNodes());
      _revealedEdges.clear();
      _highlightedEdges.clear();
      _animationMode = PropagationAnimationMode.findPath;
      _isPlaying = true;
    });
    
    // Wrap callbacks in post-frame to avoid setState during build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onAnimationModeChanged?.call('find_path');
      widget.onPathIndexChanged?.call(0);
      widget.onPopulateCompleted?.call(false);
      widget.onReduceStarted?.call(false);
      widget.onResetCurrentPaths?.call();
    });
    
    _updateGraphWithDiscoveredPaths(visualPaths);
    _updateEdgeStates();
    _pathRevealController.reset();
    
    debugPrint('🎬 Starting animation with ${paths.length} paths');
    _animateNextDiscoveredPath();
  }
  
  /// Set chosen path from execution panel control
  void setChosenPath(List<String> chosenPath) {
    // Store both pure and visual paths
    _rawChosenPath = chosenPath;
    final visualPath = _addEndpoints(chosenPath);
    
    setState(() {
      _currentChosenPath = visualPath;
    });
    
    debugPrint('🎯 Transitioning to REDUCE mode: ${visualPath.join(' -> ')}');
    _transitionToReduceMode();
  }
  
  /// Show full graph for static data (no animation)
  void _showFullGraphForStaticData() {
    
    setState(() {
      // For static data with chosen path, show only the chosen path
      if (widget.chosenPath != null && widget.chosenPath!.isNotEmpty) {
        // Add endpoints for visualization
        final visualPath = _addEndpoints(widget.chosenPath!);
        
        debugPrint('🎨 PROPAGATION: Showing chosen path with ${visualPath.length} nodes');
        _revealedNodes.clear();
        _revealedNodes.addAll(visualPath);
        _revealedNodes.addAll(_getEndpointNodes());
        
        _revealedEdges.clear();
        for (int i = 0; i < visualPath.length - 1; i++) {
          final edgeId = '${visualPath[i]}->${visualPath[i + 1]}';
          _revealedEdges.add(edgeId);
        }
        
        _highlightedEdges.clear();
        _highlightedEdges.addAll(_revealedEdges);
        
        _animationMode = PropagationAnimationMode.chosenPath;
        _isPlaying = false;
        _currentPathIndex = 1;
      } else {
        // No chosen path: show all nodes and edges
        debugPrint('🎨 PROPAGATION: No chosen path - showing all ${_nodes.length} nodes and ${_edges.length} edges');
        _revealedNodes.clear();
        _revealedNodes.addAll(_nodes.keys);
        
        _revealedEdges.clear();
        for (final edge in _edges) {
          _revealedEdges.add(edge.id);
        }
        
        _animationMode = PropagationAnimationMode.findPath;
        _isPlaying = false;
        _currentPathIndex = (widget.allPaths?.length ?? 1) - 1;
      }
    });
    
    debugPrint('🎨 PROPAGATION: After update - revealed nodes: ${_revealedNodes.length}, edges: ${_revealedEdges.length}');
    _updateEdgeStates();
  }

  /// Initialize the graph with nodes and edges
  void _initializeGraph() {
    // debugPrint('🔄 PROPAGATION: Initializing graph...');
    // debugPrint('📊 PROPAGATION: Widget allPaths: ${widget.allPaths?.length ?? 0}');
    // debugPrint('🎯 PROPAGATION: Widget chosenPath: ${widget.chosenPath?.length ?? 0}');
    // debugPrint('🎯 PROPAGATION: Discovered paths: ${_discoveredPaths.length}');
    // debugPrint('🎬 PROPAGATION: Animation mode: $_animationMode');
    
    _nodes.clear();
    _edges.clear();
    _revealedNodes.clear();
    _revealedEdges.clear();
    _highlightedEdges.clear();
    
    // Use discovered paths from streaming if available (already have endpoints),
    // fallback to widget data (need to add endpoints for visualization)
    final List<List<String>> pathsToUse = _discoveredPaths.isNotEmpty 
        ? _discoveredPaths 
        : (widget.allPaths != null ? _addEndpointsToAll(widget.allPaths!) : []);
    
    debugPrint('🔍 PROPAGATION: Paths to use: ${pathsToUse.length}');
    for (int i = 0; i < pathsToUse.length; i++) {
      debugPrint('🔍 PROPAGATION: Path $i: ${pathsToUse[i].join(' -> ')}');
    }
    
    if (pathsToUse.isEmpty) {
      debugPrint('❌ PROPAGATION: No paths available - returning early');
      return;
    }
    
    // Collect all unique nodes from paths
    final Set<String> allNodeIds = {};
    for (final path in pathsToUse) {
      allNodeIds.addAll(path);
    }
    
    // Create nodes with positions
    final List<String> nodeList = allNodeIds.toList();
    _createNodes(nodeList);
    
    // Create edges from paths
    _createEdges(pathsToUse);
    
    // Initially reveal only endpoint nodes
    final endpointNodes = _getEndpointNodes();
    _revealedNodes.addAll(endpointNodes);
    
    setState(() {});
  }

  /// Update the graph based on new data
  void _updateGraph() {
    final List<List<String>> pathsToUse = _discoveredPaths.isNotEmpty 
        ? _discoveredPaths 
        : (widget.allPaths != null ? _addEndpointsToAll(widget.allPaths!) : []);
    
    
    if (pathsToUse.isEmpty) {
      debugPrint('🔄 PROPAGATION: _updateGraph - no paths, calling _initializeGraph()');
      _initializeGraph();
      return;
    }
    
    // If we have paths but no nodes created yet, initialize the graph
    if (_nodes.isEmpty) {
      debugPrint('🔄 PROPAGATION: _updateGraph - have paths but no nodes, calling _initializeGraph()');
      _initializeGraph();
      return;
    }
    
    // Update node states based on workflow and execution
    _updateNodeStates();
    
    setState(() {});
  }

  /// Update graph with newly discovered paths from streaming
  void _updateGraphWithDiscoveredPaths(List<List<String>> paths) {
    if (paths.isEmpty) return;
    
    // Collect all unique nodes from all paths
    final Set<String> allNodeIds = {};
    for (final path in paths) {
      allNodeIds.addAll(path);
    }
    
    // Create nodes that don't exist yet
    final List<String> nodeList = allNodeIds.toList();
    final existingNodeIds = _nodes.keys.toSet();
    final newNodes = nodeList.where((id) => !existingNodeIds.contains(id)).toList();
    
    if (newNodes.isNotEmpty) {
      _createNodes(allNodeIds.toList());
    }
    
    // Create edges from all paths
    _createEdges(paths);
    
    setState(() {});
  }

  /// Animate the next discovered path (called when new paths are received)
  void _animateNextDiscoveredPath() async {
    // Check if we should continue animating
    if (!_isPlaying || _animationMode != PropagationAnimationMode.findPath) {
      debugPrint('🛑 PROPAGATION: Animation stopped - playing: $_isPlaying, mode: $_animationMode');
      return;
    }
    
    if (_currentPathIndex >= _discoveredPaths.length) {
      debugPrint('✅ PROPAGATION: All current paths animated (${_currentPathIndex}/${_discoveredPaths.length})');
      return;
    }
    
    final currentPath = _discoveredPaths[_currentPathIndex];
    final rawPath = _rawDiscoveredPaths[_currentPathIndex]; // Pure tool list for callbacks
    
    debugPrint('🎬 ANIMATING PATH ${_currentPathIndex + 1}/${_discoveredPaths.length}: ${currentPath.join(' -> ')}');
    
    // Notify execution panel that this path is being animated (pass pure path without endpoints)
    widget.onCurrentPathAdded?.call(rawPath);
    
    // Reveal nodes in this path
    _revealedNodes.addAll(currentPath);
    
    // Reveal and highlight edges in this path
    final pathEdges = <String>[];
    for (int i = 0; i < currentPath.length - 1; i++) {
      final edgeId = '${currentPath[i]}->${currentPath[i + 1]}';
      pathEdges.add(edgeId);
    }
    
    _revealedEdges.addAll(pathEdges);
    _highlightedEdges.clear();
    _highlightedEdges.addAll(pathEdges);
    
    // Update edge states
    _updateEdgeStates();
    
    // Animate path reveal
    await _pathRevealController.forward();
    _pathRevealController.reset();
    
    // Brief pause between paths
    await Future.delayed(const Duration(milliseconds: 100));
    
    // Clear highlights and move to next path
    _highlightedEdges.clear();
    _currentPathIndex++;
    
    // Notify execution panel of index change
    widget.onPathIndexChanged?.call(_currentPathIndex);
    
    setState(() {});
    
    // Continue with next path if we're still playing and in find_path mode
    if (_isPlaying && _animationMode == PropagationAnimationMode.findPath && 
        _currentPathIndex < _discoveredPaths.length) {
      debugPrint('🔄 PROPAGATION: Continuing to next path ${_currentPathIndex + 1}/${_discoveredPaths.length}...');
      _animateNextDiscoveredPath();
    } else {
      debugPrint('⏸️ PROPAGATION: Animation cycle complete - waiting for new paths (playing: $_isPlaying, mode: $_animationMode, index: $_currentPathIndex/${_discoveredPaths.length})');
      
      // Notify that populate animation is completed
      if (_currentPathIndex >= _discoveredPaths.length) {
        widget.onPopulateCompleted?.call(true);
      }
    }
  }

  /// Create nodes with calculated positions and seed-based colors
  void _createNodes(List<String> nodeIds) {
    final positions = _calculateNodePositions(nodeIds);
    
    for (int i = 0; i < nodeIds.length; i++) {
      final nodeId = nodeIds[i];
      final isEndpoint = _isEndpointNode(nodeId);
      final position = positions[i];
      
      _nodes[nodeId] = WorkflowNode(
        id: nodeId,
        title: nodeId,
        position: position,
        color: _generateNodeColor(nodeId), // Use seed-based color generation
        isEndpoint: isEndpoint,
      );
    }
  }

  /// Create edges from path data
  void _createEdges(List<List<String>> paths) {
    final Set<String> edgeIds = {};
    
    for (final path in paths) {
      for (int i = 0; i < path.length - 1; i++) {
        final from = path[i];
        final to = path[i + 1];
        final edgeId = '${from}->${to}';
        
        if (!edgeIds.contains(edgeId)) {
          edgeIds.add(edgeId);
          _edges.add(WorkflowEdge(
            id: edgeId,
            fromNodeId: from,
            toNodeId: to,
          ));
        }
      }
    }
  }

  /// Calculate positions for nodes with collision detection
  List<Offset> _calculateNodePositions(List<String> nodeIds) {
    final positions = <Offset>[];
    const canvasWidth = 800.0; // Approximate canvas width for collision calculations
    const canvasHeight = 400.0; // Approximate canvas height for collision calculations
    
    // Sort nodes so endpoints are positioned first
    final sortedNodeIds = [...nodeIds];
    sortedNodeIds.sort((a, b) {
      final aIsEndpoint = _isEndpointNode(a);
      final bIsEndpoint = _isEndpointNode(b);
      if (aIsEndpoint && !bIsEndpoint) return -1;
      if (!aIsEndpoint && bIsEndpoint) return 1;
      return a.compareTo(b); // Stable sort for consistent ordering
    });
    
    // Create a map to store positions by nodeId for final ordering
    final Map<String, Offset> positionMap = {};
    
    for (int i = 0; i < sortedNodeIds.length; i++) {
      final nodeId = sortedNodeIds[i];
      
      // Create better seed combining hash code with index for more variation
      final seed = nodeId.hashCode + (i * 1000) + nodeId.length * 100;
      final random = Random(seed);
      debugPrint('🎲 SEED: $nodeId = $seed (hash: ${nodeId.hashCode}, index: $i)');

      final position = _findNonCollidingPosition(
        nodeId,
        positions, // Pass existing positions for collision detection
        canvasWidth,
        canvasHeight,
        random,
      );
      
      positions.add(position);
      positionMap[nodeId] = position;
    }
    
    // Return positions in the original order
    return nodeIds.map((nodeId) => positionMap[nodeId]!).toList();
  }

  /// Update node states based on current workflow and execution state
  void _updateNodeStates() {
    for (final entry in _nodes.entries) {
      final nodeId = entry.key;
      final node = entry.value;
      
      final isActive = _revealedNodes.contains(nodeId);
      final isExecuting = widget.executingNodeId == nodeId;
      
      _nodes[nodeId] = node.copyWith(
        isActive: isActive,
        isExecuting: isExecuting,
      );
    }
  }

  /// Check if a node is an endpoint (input/output)
  bool _isEndpointNode(String nodeId) {
    return nodeId.contains('_IN') || nodeId.contains('_OUT');
  }

  /// Generate a seed-based color for a node
  Color _generateNodeColor(String nodeId) {
    if (_isEndpointNode(nodeId)) {
      return endpointColor;
    }
    
    // Use node name hash as seed for consistent color generation
    final hash = nodeId.hashCode.abs();
    
    // Generate HSL color with fixed saturation and lightness for consistency
    final hue = (hash % 360).toDouble();
    const saturation = 0.65; // 65% saturation for vibrant but not overwhelming colors
    const lightness = 0.75;  // 75% lightness for good contrast with text

    // Convert HSL to RGB
    final color = HSLColor.fromAHSL(1.0, hue, saturation, lightness).toColor();
    return color;
  }

  /// Check if two nodes would collide based on their positions
  bool _wouldCollide(Offset pos1, Offset pos2, double canvasWidth, double canvasHeight) {
    // Note: This is simplified collision detection using raw percentages
    // since we're calling this during positioning, not during final rendering
    final actualPos1 = Offset(
      pos1.dx * canvasWidth,
      pos1.dy * canvasHeight,
    );
    final actualPos2 = Offset(
      pos2.dx * canvasWidth,
      pos2.dy * canvasHeight,
    );
    
    // Calculate distance between centers
    final distance = (actualPos1 - actualPos2).distance;
    
    // Check if distance is less than minimum required
    return distance < minNodeDistance;
  }

  /// Find a non-colliding position for a node
  Offset _findNonCollidingPosition(
    String nodeId,
    List<Offset> existingPositions,
    double canvasWidth,
    double canvasHeight,
    Random random,
  ) {
    const maxAttempts = 50;
    const safeZoneMarginY = 0.05; // 5% margin from top/bottom edges
    
    debugPrint('🎲 POSITIONING: $nodeId - starting with ${existingPositions.length} existing positions');
    
    for (int attempt = 0; attempt < maxAttempts; attempt++) {
      Offset candidate;
      
      if (_isEndpointNode(nodeId)) {
        // Endpoints have fixed positions
        if (nodeId.contains('_IN')) {
          candidate = const Offset(0.1, 0.5);
        } else {
          candidate = const Offset(0.9, 0.5);
        }
      } else {
        // Intermediate nodes: Keep away from endpoint X positions (0.1 and 0.9)
        // Use X range 0.25 to 0.75 to avoid conflicts with IN/OUT nodes
        const intermediateMinX = 0.25; // Stay away from IMAGE_IN at 0.1
        const intermediateMaxX = 0.75; // Stay away from IMAGE_OUT at 0.9
        const intermediateRangeX = intermediateMaxX - intermediateMinX; // 0.5
        
        final x = intermediateMinX + random.nextDouble() * intermediateRangeX;
        final y = safeZoneMarginY + random.nextDouble() * (1.0 - 2 * safeZoneMarginY);
        candidate = Offset(x, y);
        debugPrint('🎲 ATTEMPT $attempt: Generated position X=$x (range: $intermediateMinX-$intermediateMaxX), Y=$y');
      }
      
      // Check for collisions with existing positions
      bool hasCollision = false;
      for (final existingPos in existingPositions) {
        if (_wouldCollide(candidate, existingPos, canvasWidth, canvasHeight)) {
          hasCollision = true;
          debugPrint('❌ COLLISION: $nodeId at ($candidate) conflicts with existing at ($existingPos)');
          break;
        }
      }
      
      if (!hasCollision) {
        debugPrint('✅ SUCCESS: $nodeId positioned at ($candidate) after $attempt attempts');
        return candidate;
      }
      
      // If endpoint collision (shouldn't happen but safety check)
      if (_isEndpointNode(nodeId)) {
        break;
      }
    }
    
    // Fallback: return candidate anyway (better than infinite loop)
    if (_isEndpointNode(nodeId)) {
      debugPrint('🔄 ENDPOINT FALLBACK: $nodeId');
      return nodeId.contains('_IN') ? const Offset(0.1, 0.5) : const Offset(0.9, 0.5);
    } else {
      // Fallback with same X constraints as main positioning logic
      const intermediateMinX = 0.25;
      const intermediateMaxX = 0.75;
      const intermediateRangeX = intermediateMaxX - intermediateMinX;
      
      final fallbackX = intermediateMinX + random.nextDouble() * intermediateRangeX;
      final fallbackY = safeZoneMarginY + random.nextDouble() * (1.0 - 2 * safeZoneMarginY);
      final fallback = Offset(fallbackX, fallbackY);
      debugPrint('🔄 FALLBACK: $nodeId forced to position ($fallback) after $maxAttempts failed attempts');
      return fallback;
    }
  }

  /// Get endpoint node IDs
  Set<String> _getEndpointNodes() {
    return _nodes.keys.where(_isEndpointNode).toSet();
  }

  /// Animate revealing the next path
  void _animateNextPath() async {
    if (_currentPathIndex >= widget.allPaths!.length) {
      // All paths revealed, transition to next mode if needed
      if (widget.chosenPath != null && widget.chosenPath!.isNotEmpty) {
        _transitionToReduceMode();
      }
      return;
    }
    
    final currentPath = widget.allPaths![_currentPathIndex];
    
    // Add path to ExecutionPanel's currentPaths for Pipeline tracking
    widget.onCurrentPathAdded?.call(currentPath);
    
    // Update execution panel's current path index for Pipeline highlighting
    widget.onPathIndexChanged?.call(_currentPathIndex);
    
    // Reveal nodes in this path
    _revealedNodes.addAll(currentPath);
    
    // Reveal and highlight edges in this path
    final pathEdges = <String>[];
    for (int i = 0; i < currentPath.length - 1; i++) {
      final edgeId = '${currentPath[i]}->${currentPath[i + 1]}';
      pathEdges.add(edgeId);
    }
    
    _revealedEdges.addAll(pathEdges);
    _highlightedEdges.clear();
    _highlightedEdges.addAll(pathEdges);
    
    // Update edge states
    _updateEdgeStates();
    
    // Animate path reveal
    await _pathRevealController.forward();
    
    // Brief pause between paths
    await Future.delayed(const Duration(milliseconds: 100));
    
    // Clear highlights and move to next path
    _highlightedEdges.clear();
    _currentPathIndex++;
    
    setState(() {});
    
    // Continue with next path
    if (_isPlaying) {
      _animateNextPath();
    }
  }

  /// Update edge visibility and highlighting states
  void _updateEdgeStates() {
    for (int i = 0; i < _edges.length; i++) {
      final edge = _edges[i];
      _edges[i] = edge.copyWith(
        isVisible: _revealedEdges.contains(edge.id),
        isHighlighted: _highlightedEdges.contains(edge.id),
      );
    }
  }

  /// Transition to reduce mode (eliminating paths)
  void _transitionToReduceMode() {
    setState(() {
      _animationMode = PropagationAnimationMode.reduce;
      _currentPathIndex = 0;
    });
    
    // Notify execution panel of mode change to reduce
    // Defer callbacks to avoid calling setState during build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onAnimationModeChanged?.call('reduce');
      widget.onReduceStarted?.call(true);
    });
    
    // Start eliminating paths one by one
    _eliminateNextPath();
  }
  
  /// Eliminate paths one by one (reduce animation)
  void _eliminateNextPath() async {
    // Use raw path for comparison (pure tool lists, no endpoints)
    final chosenPath = _rawChosenPath ?? widget.chosenPath;
    
    if (chosenPath == null || chosenPath.isEmpty) {
      _transitionToChosenPathMode();
      return;
    }
    
    // Get all paths that need to be eliminated (all except chosen)
    final allPaths = widget.allPaths ?? [];
    final pathsToEliminate = allPaths.where((path) {
      return path.join('->') != chosenPath.join('->');
    }).toList();
    
    if (_currentPathIndex >= pathsToEliminate.length) {
      // All paths eliminated - transition to chosen path mode
      _transitionToChosenPathMode();
      return;
    }
    
    final pathToEliminate = pathsToEliminate[_currentPathIndex];
    
    // Find global index in allPaths for Pipeline highlighting
    final globalIndex = allPaths.indexWhere((p) => p.join('->') == pathToEliminate.join('->'));
    debugPrint('🗑️  ELIMINATING: Path $_currentPathIndex (global index: $globalIndex) - ${pathToEliminate.join(" -> ")}');
    
    // Update execution panel's current path index for Pipeline highlighting
    widget.onPathIndexChanged?.call(globalIndex);
    
    // Step 1: Highlight the path to be eliminated
    final pathEdges = <String>[];
    for (int i = 0; i < pathToEliminate.length - 1; i++) {
      pathEdges.add('${pathToEliminate[i]}->${pathToEliminate[i + 1]}');
    }
    
    setState(() {
      _highlightedEdges.clear();
      _highlightedEdges.addAll(pathEdges);
    });
    
    _updateEdgeStates();
    
    // Step 2: Animate the highlight (match populate timing)
    await _pathRevealController.forward();
    _pathRevealController.reset();
    
    // Step 3: Remove the path while keeping it highlighted
    widget.onCurrentPathRemoved?.call(pathToEliminate);
    
    setState(() {
      // Remove path edges if they're not used by other remaining paths or chosen path
      final edgesInOtherPaths = <String>{};
      
      // Collect edges from all remaining paths (not yet eliminated)
      for (int i = _currentPathIndex + 1; i < pathsToEliminate.length; i++) {
        final remainingPath = pathsToEliminate[i];
        for (int j = 0; j < remainingPath.length - 1; j++) {
          edgesInOtherPaths.add('${remainingPath[j]}->${remainingPath[j + 1]}');
        }
      }
      
      // Also keep edges from the chosen path (use visual path with endpoints)
      final visualChosenPath = _addEndpoints(chosenPath);
      for (int i = 0; i < visualChosenPath.length - 1; i++) {
        edgesInOtherPaths.add('${visualChosenPath[i]}->${visualChosenPath[i + 1]}');
      }
      
      // Remove edges that aren't used by other paths
      for (final edge in pathEdges) {
        if (!edgesInOtherPaths.contains(edge)) {
          _revealedEdges.remove(edge);
        }
      }
      
      // Remove nodes that are no longer connected to any edge
      final connectedNodes = <String>{};
      for (final edge in _revealedEdges) {
        final parts = edge.split('->');
        if (parts.length == 2) {
          connectedNodes.add(parts[0]);
          connectedNodes.add(parts[1]);
        }
      }
      
      // Keep endpoint nodes always visible
      connectedNodes.addAll(_getEndpointNodes());
      _revealedNodes.retainWhere((node) => connectedNodes.contains(node));
    });
    
    _updateEdgeStates();
    
    // Step 4: Brief pause before clearing highlight (match populate timing)
    await Future.delayed(const Duration(milliseconds: 100));
    
    // Clear highlights
    setState(() {
      _highlightedEdges.clear();
    });
    
    _updateEdgeStates();
    
    // Move to next path
    setState(() {
      _currentPathIndex++;
    });
    
    // Continue eliminating
    _eliminateNextPath();
  }

  /// Transition to chosen path mode (static display)
  void _transitionToChosenPathMode() {
    // Notify execution panel that reduce animation is complete
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onReduceCompleted?.call();
    });
    
    setState(() {
      _animationMode = PropagationAnimationMode.chosenPath;
      
      // Ensure we have a visual path (with endpoints) for edge creation
      List<String>? visualPath;
      if (_currentChosenPath != null) {
        // Already has endpoints from reduce animation
        visualPath = _currentChosenPath;
      } else if (widget.chosenPath != null) {
        // Raw path - add endpoints for visualization
        visualPath = _addEndpoints(widget.chosenPath!);
      }
      
      if (visualPath != null) {
        // Show only chosen path nodes and edges
        _revealedNodes.clear();
        _revealedNodes.addAll(visualPath);
        
        _revealedEdges.clear();
        for (int i = 0; i < visualPath.length - 1; i++) {
          final edgeId = '${visualPath[i]}->${visualPath[i + 1]}';
          _revealedEdges.add(edgeId);
        }
        
        _highlightedEdges.clear();
        _highlightedEdges.addAll(_revealedEdges);
        
        _updateEdgeStates();
      }
    });
    
    // Notify execution panel of mode change to chosen_path
    // Defer callback to avoid calling setState during build
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onAnimationModeChanged?.call('chosen_path');
    });
  }

  /// Toggle animation play/pause
  void _togglePlayPause() {
    setState(() {
      _isPlaying = !_isPlaying;
    });
    
    if (_isPlaying && _animationMode == PropagationAnimationMode.findPath) {
      _animateNextPath();
    }
  }

  /// Restart the animation (public method for external control)
  /// Restart animation (called by execution panel)
  void restart() {
    if (widget.allPaths != null && widget.allPaths!.isNotEmpty) {
      startPathAnimation(widget.allPaths!);
    } else {
      setState(() {
        _currentPathIndex = 0;
        _isPlaying = false;
        _animationMode = PropagationAnimationMode.findPath;
        _revealedNodes.clear();
        _revealedEdges.clear();
        _highlightedEdges.clear();
        _revealedNodes.addAll(_getEndpointNodes());
      });
      
      // Defer callbacks to avoid calling setState during build
      WidgetsBinding.instance.addPostFrameCallback((_) {
        widget.onAnimationModeChanged?.call('find_path');
        widget.onPathIndexChanged?.call(0);
        widget.onPopulateCompleted?.call(false);
        widget.onReduceStarted?.call(false);
        widget.onResetCurrentPaths?.call();
      });
      
      _pathRevealController.reset();
      _updateEdgeStates();
    }
  }
  
  void _restartAnimation() {
    // Internal restart for button clicks - delegate to public restart
    restart();
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
        children: [
          // Controls
          _buildControls(),
          // Graph canvas
          Expanded(
            child: _buildGraphCanvas(),
          ),
        ],
      ),
    );
  }

  /// Build the control buttons
  Widget _buildControls() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: const BoxDecoration(
        color: Color(0x70FFFFFF),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(16),
          topRight: Radius.circular(16),
        ),
      ),
      child: Row(
        children: [
          if (_animationMode == PropagationAnimationMode.findPath) ...[
            // Play/Pause button
            ElevatedButton(
              onPressed: _togglePlayPause,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Colors.black87,
                elevation: 0,
                side: const BorderSide(color: Color(0xFFE2E8F0)),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              ),
              child: Text(
                _isPlaying ? 'Pause' : 'Play',
                style: const TextStyle(fontSize: 11),
              ),
            ),
            const SizedBox(width: 6),
            // Restart button
            ElevatedButton(
              onPressed: _restartAnimation,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Colors.black87,
                elevation: 0,
                side: const BorderSide(color: Color(0xFFE2E8F0)),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              ),
              child: const Text(
                'Restart',
                style: TextStyle(fontSize: 11),
              ),
            ),
            const SizedBox(width: 12),
          ],
          // Status text - wrapped in Expanded to prevent overflow
          Expanded(
            child: Text(
              _getStatusText(),
              style: const TextStyle(
                fontSize: 11,
                color: Color(0xFF64748B),
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  /// Get status text based on current animation state
  String _getStatusText() {
    switch (_animationMode) {
      case PropagationAnimationMode.findPath:
        final total = _discoveredPaths.isNotEmpty ? _discoveredPaths.length : (widget.allPaths?.length ?? 0);
        if (total == 0) {
          return 'Waiting for path discovery...';
        }
        
        final current = (_currentPathIndex < total) ? _currentPathIndex + 1 : total;
        final isStreaming = widget.streamingService != null && _discoveredPaths.isNotEmpty;
        
        if (isStreaming) {
          // Show real-time indicator when streaming
          if (_currentPathIndex >= total) {
            return 'Real-time: Waiting for new paths... 🔄 ($total paths ready)';
          } else {
            return 'Real-time: Animating paths... 🔄 ($current/$total)';
          }
        } else {
          return 'Revealing paths ($current/$total)';
        }
      case PropagationAnimationMode.reduce:
        return 'Eliminating paths...';
      case PropagationAnimationMode.chosenPath:
        return 'Selected path - Static';
    }
  }

  /// Build the main graph canvas
  Widget _buildGraphCanvas() {
    if (_nodes.isEmpty) {
      return const Center(
        child: Text(
          'Waiting for paths...',
          style: TextStyle(
            color: Colors.black,
            fontSize: 14,
          ),
        ),
      );
    }

    return ClipRect(
      child: AnimatedBuilder(
        animation: Listenable.merge([_pathRevealAnimation, _nodeScaleAnimation, _edgeAnimation]),
        builder: (context, child) {
          return LayoutBuilder(
            builder: (context, constraints) {
              // Get canvas dimensions
              final canvasWidth = constraints.maxWidth;
              final canvasHeight = constraints.maxHeight;
              
              return MouseRegion(
                cursor: SystemMouseCursors.basic, // Default cursor
                child: GestureDetector(
                  onTapDown: (details) {
                    // Find which node was tapped based on position
                    final tapPosition = details.localPosition;
                    
                    // Convert percentage positions to pixel positions (same as _GraphPainter)
                    const nodeMargin = 40.0;
                    final availableWidth = canvasWidth - (nodeMargin * 2);
                    final availableHeight = canvasHeight - (nodeMargin * 2);
                    
                    for (final node in _nodes.values) {
                      if (!_revealedNodes.contains(node.id)) continue; // Only allow clicking revealed nodes
                      
                      // Skip endpoint nodes (IMAGE_IN, IMAGE_OUT, TEXT_IN, TEXT_OUT, etc.)
                      if (_isEndpointNode(node.id)) continue;
                      
                      // Convert node's percentage position to pixel position
                      final actualX = nodeMargin + (node.position.dx * availableWidth);
                      final actualY = nodeMargin + (node.position.dy * availableHeight);
                      final actualPosition = Offset(actualX, actualY);
                      
                      // Check if tap is within node bounds (40x24 node size from painter)
                      final nodeRect = Rect.fromCenter(
                        center: actualPosition,
                        width: 40,
                        height: 24,
                      );
                      
                      if (nodeRect.contains(tapPosition)) {
                        // Find the step index from the chosen path
                        if (widget.chosenPath != null && widget.onToolSelected != null) {
                          final pathIndex = widget.chosenPath!.indexOf(node.id);
                          if (pathIndex >= 0) {
                            // Convert 0-based array index to 1-based step index
                            // chosenPath is pure tool list: [image_ocr, translate, erase, ...]
                            // Backend files are 1-based: 01_image_ocr, 02_translate, 03_erase, ...
                            final stepIndex = pathIndex + 1;
                            widget.onToolSelected!(node.id, stepIndex);
                            debugPrint('🖱️ NODE TAPPED: ${node.id} at path index $pathIndex, step index $stepIndex');
                          }
                        }
                        break;
                      }
                    }
                  },
                  child: MouseRegion(
                    hitTestBehavior: HitTestBehavior.translucent,
                    onHover: (event) {
                      // Update cursor based on hover position
                      final hoverPosition = event.localPosition;
                      
                      // Convert percentage positions to pixel positions
                      const nodeMargin = 40.0;
                      final availableWidth = canvasWidth - (nodeMargin * 2);
                      final availableHeight = canvasHeight - (nodeMargin * 2);
                      
                      bool isOverClickableNode = false;
                      
                      for (final node in _nodes.values) {
                        if (!_revealedNodes.contains(node.id)) continue;
                        
                        // Skip endpoint nodes
                        if (_isEndpointNode(node.id)) continue;
                        
                        // Convert node's percentage position to pixel position
                        final actualX = nodeMargin + (node.position.dx * availableWidth);
                        final actualY = nodeMargin + (node.position.dy * availableHeight);
                        final actualPosition = Offset(actualX, actualY);
                        
                        final nodeRect = Rect.fromCenter(
                          center: actualPosition,
                          width: 40,
                          height: 24,
                        );
                        
                        if (nodeRect.contains(hoverPosition)) {
                          isOverClickableNode = true;
                          break;
                        }
                      }
                      
                      // This will be handled by the cursor parameter in the wrapping MouseRegion
                      setState(() {
                        _isHoveringClickableNode = isOverClickableNode;
                      });
                    },
                    cursor: _isHoveringClickableNode ? SystemMouseCursors.click : SystemMouseCursors.basic,
                    child: CustomPaint(
                      painter: _GraphPainter(
                        nodes: _nodes.values.toList(),
                        edges: _edges,
                        revealedNodes: _revealedNodes,
                        revealedEdges: _revealedEdges,
                        highlightedEdges: _highlightedEdges,
                        executingNodeId: widget.executingNodeId,
                        pathRevealProgress: _pathRevealAnimation.value,
                        nodeScaleAnimation: _nodeScaleAnimation.value,
                        edgeAnimation: _edgeAnimation.value,
                      ),
                      child: Container(),
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}

/// Custom painter for drawing the workflow graph
class _GraphPainter extends CustomPainter {
  final List<WorkflowNode> nodes;
  final List<WorkflowEdge> edges;
  final Set<String> revealedNodes;
  final Set<String> revealedEdges;
  final Set<String> highlightedEdges;
  final String? executingNodeId;
  final double pathRevealProgress;
  final double nodeScaleAnimation;
  final double edgeAnimation;

  _GraphPainter({
    required this.nodes,
    required this.edges,
    required this.revealedNodes,
    required this.revealedEdges,
    required this.highlightedEdges,
    this.executingNodeId,
    required this.pathRevealProgress,
    required this.nodeScaleAnimation,
    required this.edgeAnimation,
  });

  @override
  void paint(Canvas canvas, Size size) {
    // Convert percentage positions to actual pixel positions
    final actualNodePositions = <String, Offset>{};
    final nodeMargin = 40.0; // Margin from edges
    final availableWidth = size.width - (nodeMargin * 2);
    final availableHeight = size.height - (nodeMargin * 2);
    
    for (final node in nodes) {
      // All nodes now use direct positioning - constraints applied during generation
      final actualX = nodeMargin + (node.position.dx * availableWidth);
      final actualY = nodeMargin + (node.position.dy * availableHeight);
      actualNodePositions[node.id] = Offset(actualX, actualY);
    }
    
    // Update node positions with actual coordinates
    final actualNodes = nodes.map((node) {
      final actualPosition = actualNodePositions[node.id]!;
      return node.copyWith(position: actualPosition);
    }).toList();

    // Draw edges first (so they appear behind nodes)
    _drawEdges(canvas, actualNodePositions);
    
    // Draw nodes with actual positions
    _drawNodesWithActualPositions(canvas, actualNodes);
  }

  /// Draw all edges
  void _drawEdges(Canvas canvas, Map<String, Offset> nodePositions) {
    for (final edge in edges) {
      if (!edge.isVisible) continue;
      
      final fromPos = nodePositions[edge.fromNodeId];
      final toPos = nodePositions[edge.toNodeId];
      
      if (fromPos == null || toPos == null) continue;
      
      _drawEdge(canvas, fromPos, toPos, edge.isHighlighted);
    }
  }

  /// Draw a single edge as a curved path
  void _drawEdge(Canvas canvas, Offset from, Offset to, bool isHighlighted) {
    final paint = Paint()
      ..color = isHighlighted ? _PropagationState.activeEdgeColor : _PropagationState.normalEdgeColor
      ..strokeWidth = isHighlighted ? _PropagationState.highlightedEdgeStrokeWidth : _PropagationState.edgeStrokeWidth
      ..style = PaintingStyle.stroke;

    // Create a curved path
    final path = Path();
    path.moveTo(from.dx, from.dy);
    
    // Calculate control points for bezier curve
    final dx = (to.dx - from.dx) / 2;
    final c1 = Offset(from.dx + dx, from.dy);
    final c2 = Offset(to.dx - dx, to.dy);
    
    path.cubicTo(c1.dx, c1.dy, c2.dx, c2.dy, to.dx, to.dy);
    
    canvas.drawPath(path, paint);
  }

  /// Draw all nodes with actual positions
  void _drawNodesWithActualPositions(Canvas canvas, List<WorkflowNode> actualNodes) {
    for (final node in actualNodes) {
      if (!revealedNodes.contains(node.id)) continue;
      
      _drawNode(canvas, node);
    }
  }

  /// Draw a single node
  void _drawNode(Canvas canvas, WorkflowNode node) {
    final isExecuting = executingNodeId == node.id;
    final scale = isExecuting ? nodeScaleAnimation : 1.0;
    
    // Node background
    final rect = RRect.fromRectAndRadius(
      Rect.fromCenter(
        center: node.position,
        width: _PropagationState.nodeWidth * scale,
        height: _PropagationState.nodeHeight * scale,
      ),
      const Radius.circular(10),
    );
    
    final paint = Paint()
      ..color = node.color
      ..style = PaintingStyle.fill;
    
    canvas.drawRRect(rect, paint);
    
    // Executing node glow effect (multi-layer for more visibility)
    if (isExecuting) {
      // Outer glow (large, soft)
      final outerGlowPaint = Paint()
        ..color = _PropagationState.activeEdgeColor.withOpacity(0.2)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 6
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
      
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(
            center: node.position,
            width: (_PropagationState.nodeWidth + 12) * scale,
            height: (_PropagationState.nodeHeight + 12) * scale,
          ),
          const Radius.circular(14),
        ),
        outerGlowPaint,
      );
      
      // Middle glow (medium, brighter)
      final middleGlowPaint = Paint()
        ..color = _PropagationState.activeEdgeColor.withOpacity(0.5)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3;
      
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(
            center: node.position,
            width: (_PropagationState.nodeWidth + 6) * scale,
            height: (_PropagationState.nodeHeight + 6) * scale,
          ),
          const Radius.circular(12),
        ),
        middleGlowPaint,
      );
      
      // Inner glow (tight, brightest)
      final innerGlowPaint = Paint()
        ..color = _PropagationState.activeEdgeColor.withOpacity(0.8)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2;
      
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(
            center: node.position,
            width: (_PropagationState.nodeWidth + 2) * scale,
            height: (_PropagationState.nodeHeight + 2) * scale,
          ),
          const Radius.circular(11),
        ),
        innerGlowPaint,
      );
    }
    
    // Node text
    final textPainter = TextPainter(
      text: TextSpan(
        text: node.title,
        style: TextStyle(
          color: Colors.black,
          fontSize: _PropagationState.fontSize,
          fontWeight: FontWeight.w500,
        ),
      ),
      textDirection: TextDirection.ltr,
    );
    
    textPainter.layout();
    
    final textOffset = Offset(
      node.position.dx - textPainter.width / 2,
      node.position.dy - textPainter.height / 2,
    );
    
    textPainter.paint(canvas, textOffset);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) {
    return true; // Always repaint for animations
  }
}
