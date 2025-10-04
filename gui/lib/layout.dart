import 'package:flutter/material.dart';
import 'package:gui/data/services/streaming_service.dart';
import 'widgets/chat/sidebar.dart';
import 'widgets/chat_panel.dart';
import 'widgets/execution_panel.dart';
import 'widgets/common/resizable_divider.dart';

class Layout extends StatefulWidget {
  final Widget child;

  const Layout({
    super.key,
    required this.child,
  });

  @override
  State<Layout> createState() => _LayoutState();
}

class _LayoutState extends State<Layout> with SingleTickerProviderStateMixin {
  bool _isSidebarCollapsed = false;
  bool _isExecutionPanelCollapsed = true; // Start collapsed by default
  late AnimationController _animationController;
  late Animation<double> _sidebarAnimation;
  String? _selectedChatId;
  final GlobalKey<SidebarState> _sidebarKey = GlobalKey<SidebarState>();
  final StreamingService _streamingService = StreamingService();
  
  // Execution panel state
  Map<String, dynamic>? _selectedExecutionState;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _sidebarAnimation = Tween<double>(
      begin: 256.0, // w-64 = 256px
      end: 48.0,     // w-12 = 48px
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    ));
    
    // Listen to pathDiscovery to auto-expand execution panel
    _streamingService.pathDiscovery.listen((paths) {
      debugPrint('🔔 LAYOUT: pathDiscovery received - ${paths.length} paths, collapsed: $_isExecutionPanelCollapsed');
      if (_isExecutionPanelCollapsed && paths.isNotEmpty) {
        debugPrint('🔓 LAYOUT: Auto-expanding execution panel');
        setState(() {
          _isExecutionPanelCollapsed = false;
        });
      }
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    _streamingService.dispose();
    super.dispose();
  }

  void _toggleSidebar() {
    setState(() {
      _isSidebarCollapsed = !_isSidebarCollapsed;
      if (_isSidebarCollapsed) {
        _animationController.forward();
      } else {
        _animationController.reverse();
      }
    });
  }

  void _toggleExecutionPanel() {
    setState(() {
      _isExecutionPanelCollapsed = !_isExecutionPanelCollapsed;
    });
  }

  void _handleSelectChat(String chatId) {
    // Handle empty string as null (no chat selected)
    final newChatId = chatId.isEmpty ? null : chatId;
    
    setState(() {
      _selectedChatId = newChatId;
      // Clear execution selection when switching chats
      _selectedExecutionState = null;
      // Collapse execution panel since no summary card is clicked yet
      _isExecutionPanelCollapsed = true;
    });
    
    if (newChatId != null) {
      // Refresh sidebar when switching chats to ensure consistency
      _sidebarKey.currentState?.refreshChatList();
    }
  }

  void _handleExecutionSelected(int messageId, Map<String, dynamic> stateData) {
    setState(() {
      _selectedExecutionState = stateData;
      // Auto-expand execution panel when user clicks a summary card
      if (_isExecutionPanelCollapsed) {
        _isExecutionPanelCollapsed = false;
      }
    });
  }

  void _clearExecutionSelection() {
    setState(() {
      _selectedExecutionState = null;
    });
  }

  String? _extractExecutionOutputPath(Map<String, dynamic>? stateData) {
    if (stateData == null) return null;
    return stateData['execution_output_path']?.toString();
  }

  List<List<String>> _extractAllPaths(Map<String, dynamic>? stateData) {
    if (stateData == null) return [];
    
    try {
      final allPaths = stateData['all_paths'];
      if (allPaths == null || allPaths is! List) return [];
      
      // Extract paths as-is (just tool names, no endpoints)
      final List<List<String>> result = [];
      for (final pathData in allPaths) {
        if (pathData is! List) continue;
        
        final List<String> path = [];
        for (final tool in pathData) {
          if (tool is Map && tool.containsKey('name')) {
            final name = tool['name']?.toString();
            if (name != null) path.add(name);
          }
        }
        if (path.isNotEmpty) result.add(path);
      }
      return result;
    } catch (e) {
      debugPrint('❌ Error extracting all_paths: $e');
      return [];
    }
  }

  List<String>? _extractChosenPath(Map<String, dynamic>? stateData) {
    if (stateData == null) return null;
    
    try {
      final chosenPath = stateData['chosen_path'];
      if (chosenPath == null || chosenPath is! List || chosenPath.isEmpty) return null;
      
      // Extract path as-is (just tool names, no endpoints)
      final List<String> result = [];
      for (final tool in chosenPath) {
        if (tool is Map && tool.containsKey('name')) {
          final name = tool['name']?.toString();
          if (name != null) result.add(name);
        }
      }
      
      // If no tools, treat as no chosen path
      if (result.isEmpty) return null;
      
      return result;
    } catch (e) {
      debugPrint('❌ Error extracting chosen_path: $e');
      return null;
    }
  }

  String? _extractInputType(Map<String, dynamic>? stateData) {
    if (stateData == null) return null;
    return stateData['input_type']?.toString().toUpperCase();
  }

  String? _extractOutputType(Map<String, dynamic>? stateData) {
    if (stateData == null) return null;
    final typeSavepoint = stateData['type_savepoint'];
    if (typeSavepoint is List && typeSavepoint.isNotEmpty) {
      return typeSavepoint.last.toString().toUpperCase();
    }
    return null;
  }

  Future<void> _handleTitleUpdate(String newTitle) async {
    // Trigger animation directly without refreshing sidebar
    try {
      await _sidebarKey.currentState?.animateTitleUpdate(_selectedChatId!, newTitle);
    } catch (e) {
      debugPrint('❌ LAYOUT: Failed to trigger title animation: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Row(
        children: [
          // Sidebar
          AnimatedBuilder(
            animation: _sidebarAnimation,
            builder: (context, child) {
              final double width = _sidebarAnimation.value;
              return Container(
                width: width,
                height: double.infinity,
                decoration: BoxDecoration(
                  color: Colors.white,
                  border: Border(
                    right: (_isSidebarCollapsed == false)
                        ? BorderSide(color: Colors.grey.shade200, width: 1)
                        : BorderSide.none,
                  ),
                ),
                child: Sidebar(
                  key: _sidebarKey,
                  isCollapsed: _isSidebarCollapsed,
                  onToggle: _toggleSidebar,
                  width: width,
                  onSelect: _handleSelectChat,
                ),
              );
            },
          ),
          
          // Main Content Area
          Expanded(
            child: _isExecutionPanelCollapsed
                  ? Container(
                      decoration: BoxDecoration(
                        color: Colors.white,
                        border: Border(
                          right: BorderSide(color: Colors.grey.shade200, width: 1),
                        ),
                      ),
                      child: ChatPanel(
                    chatId: _selectedChatId,
                    onTitleUpdated: _handleTitleUpdate,
                    streamingService: _streamingService,
                    onExecutionSelected: _handleExecutionSelected,
                    onMessageSent: _clearExecutionSelection,
                  ),
                    )
                  : ResizablePanels(
                  isVertical: false,
                  initialRatio: 0.5,
                  minFirstPanelRatio: 0.3,
                  maxFirstPanelRatio: 0.7,
                  dividerThickness: 6.0,
                  dividerColor: Colors.grey.shade200,
                  dividerHoverColor: Colors.grey.shade300,
                  firstPanel: Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      border: Border(
                        right: BorderSide(color: Colors.grey.shade200, width: 1),
                      ),
                    ),
                    child: ChatPanel(
                      chatId: _selectedChatId,
                      onTitleUpdated: _handleTitleUpdate,
                      streamingService: _streamingService,
                      onExecutionSelected: _handleExecutionSelected,
                      onMessageSent: _clearExecutionSelection,
                    ),
                  ),
                  secondPanel: ExecutionPanel(
                    streamingService: _selectedExecutionState != null ? null : _streamingService,
                    chatId: _selectedChatId,
                    staticExecutionOutputPath: _extractExecutionOutputPath(_selectedExecutionState),
                    staticAllPaths: _selectedExecutionState != null ? _extractAllPaths(_selectedExecutionState) : null,
                    staticChosenPath: _selectedExecutionState != null ? _extractChosenPath(_selectedExecutionState) : null,
                    inputType: _extractInputType(_selectedExecutionState),
                    outputType: _extractOutputType(_selectedExecutionState),
                    onClose: _toggleExecutionPanel,
                  ),
                ),
          ),
        ],
      ),
    );
  }
}
