import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:gui/core/config.dart';
import '../models/file_attachment.dart';

/// Represents different types of streaming events from the orchestrator
enum StreamEventType {
  updates,
  messages,
  custom,
  persisted,
  error,
}

/// Represents a parsed streaming event
class StreamEvent {
  final StreamEventType type;
  final dynamic data;

  const StreamEvent({
    required this.type,
    required this.data,
  });

  factory StreamEvent.fromJson(Map<String, dynamic> json) {
    final typeStr = json['type'] as String? ?? 'unknown';
    final type = _parseEventType(typeStr);
    final data = json['data']; // Keep original type - can be Map, List, String, etc.

    return StreamEvent(
      type: type,
      data: data,
    );
  }

  static StreamEventType _parseEventType(String typeStr) {
    switch (typeStr) {
      case 'updates':
        return StreamEventType.updates;
      case 'messages':
        return StreamEventType.messages;
      case 'custom':
        return StreamEventType.custom;
      case 'persisted':
        return StreamEventType.persisted;
      case 'error':
        return StreamEventType.error;
      default:
        return StreamEventType.custom;
    }
  }
}

/// Represents a console output entry
class ConsoleEntry {
  final String timestamp;
  final String type; // 'stdout' or 'stderr'
  final String line;
  final int? stepIndex;
  final String? toolName;

  const ConsoleEntry({
    required this.timestamp,
    required this.type,
    required this.line,
    this.stepIndex,
    this.toolName,
  });
}

/// Represents executor state for a specific tool/step
class ExecutorStepData {
  final String toolName;
  final int stepIndex;
  final String? workspaceDir;
  final String? status; // 'start' or 'end'
  final String? outputFilePath;
  final String? mimeType;

  const ExecutorStepData({
    required this.toolName,
    required this.stepIndex,
    this.workspaceDir,
    this.status,
    this.outputFilePath,
    this.mimeType,
  });
}

/// Represents a workflow section/stage in the orchestrator process
class WorkflowSection {
  final String node;
  final String title;
  final String status;
  final String reasoningContent;
  final double? thinkingTime;
  final bool isThinking;
  final bool isAutoExpanded; // Whether this section should be auto-expanded during streaming
  final String? clarification;

  const WorkflowSection({
    required this.node,
    required this.title,
    required this.status,
    required this.reasoningContent,
    this.thinkingTime,
    required this.isThinking,
    this.isAutoExpanded = false,
    this.clarification,
  });

  WorkflowSection copyWith({
    String? node,
    String? title,
    String? status,
    String? reasoningContent,
    double? thinkingTime,
    bool? isThinking,
    bool? isAutoExpanded,
    String? clarification,
  }) {
    return WorkflowSection(
      node: node ?? this.node,
      title: title ?? this.title,
      status: status ?? this.status,
      reasoningContent: reasoningContent ?? this.reasoningContent,
      thinkingTime: thinkingTime ?? this.thinkingTime,
      isThinking: isThinking ?? this.isThinking,
      isAutoExpanded: isAutoExpanded ?? this.isAutoExpanded,
      clarification: clarification ?? this.clarification,
    );
  }
}

/// Represents the complete workflow state with all sections
class WorkflowState {
  final Map<String, WorkflowSection> sections;
  final List<String> sectionOrder;

  const WorkflowState({
    required this.sections,
    required this.sectionOrder,
  });

  WorkflowState copyWith({
    Map<String, WorkflowSection>? sections,
    List<String>? sectionOrder,
  }) {
    return WorkflowState(
      sections: sections ?? this.sections,
      sectionOrder: sectionOrder ?? this.sectionOrder,
    );
  }
}

/// Represents the current message being streamed
class StreamingMessage {
  final String id;
  final String role;
  final String content;
  final WorkflowState? workflow;
  final Map<String, dynamic>? state;
  final bool isPersisted; // Flag to indicate if this is the final persisted message
  final String? type; // Message type: 'question' or 'response'

  const StreamingMessage({
    required this.id,
    required this.role,
    required this.content,
    this.workflow,
    this.state,
    this.isPersisted = false,
    this.type,
  });

  StreamingMessage copyWith({
    String? id,
    String? role,
    String? content,
    WorkflowState? workflow,
    Map<String, dynamic>? state,
    bool? isPersisted,
    String? type,
  }) {
    return StreamingMessage(
      id: id ?? this.id,
      role: role ?? this.role,
      content: content ?? this.content,
      workflow: workflow ?? this.workflow,
      state: state ?? this.state,
      isPersisted: isPersisted ?? this.isPersisted,
      type: type ?? this.type,
    );
  }
}

/// Service for handling streaming responses from the message API
class StreamingService {
  final StreamController<StreamEvent> _eventController = StreamController<StreamEvent>.broadcast();
  final StreamController<StreamingMessage> _messageController = StreamController<StreamingMessage>.broadcast();
  final StreamController<WorkflowState> _workflowController = StreamController<WorkflowState>.broadcast();
  final StreamController<String> _chatTitleController = StreamController<String>.broadcast();
  final StreamController<List<List<String>>> _pathDiscoveryController = StreamController<List<List<String>>>.broadcast();
  final StreamController<List<String>> _chosenPathController = StreamController<List<String>>.broadcast();
  
  // Executor event streams
  final StreamController<ConsoleEntry> _consoleController = StreamController<ConsoleEntry>.broadcast();
  final StreamController<ExecutorStepData> _executorStepController = StreamController<ExecutorStepData>.broadcast();
  final StreamController<String> _currentToolController = StreamController<String>.broadcast();
  final StreamController<Map<String, int>> _executionProgressController = StreamController<Map<String, int>>.broadcast();
  
  // Node titles mapping (matching Next.js frontend)
  final Map<String, String> _nodeTitles = {
    'precedent': 'Searching for precedent...',
    'classify': 'Classifying...',
    'find_path': 'Searching for possible paths...',
    'route': 'Selecting the path...',
    'execute': 'Executing...',
    'finalize': 'Formatting response...',
  };
  
  Stream<StreamEvent> get events => _eventController.stream;
  Stream<StreamingMessage> get messages => _messageController.stream;
  Stream<WorkflowState> get workflow => _workflowController.stream;
  Stream<String> get chatTitleUpdates => _chatTitleController.stream;
  Stream<List<List<String>>> get pathDiscovery => _pathDiscoveryController.stream;
  
  // Expose last pathDiscovery for late subscribers
  List<List<String>>? get lastPathDiscovery => _lastPathDiscovery;
  
  // Expose current message state for widgets that need it
  Map<String, dynamic>? get currentState => _currentMessage?.state;
  Stream<List<String>> get chosenPath => _chosenPathController.stream;
  
  // Executor event streams
  Stream<ConsoleEntry> get consoleOutput => _consoleController.stream;
  Stream<ExecutorStepData> get executorSteps => _executorStepController.stream;
  Stream<String> get currentTool => _currentToolController.stream;
  Stream<Map<String, int>> get executionProgress => _executionProgressController.stream;
  
  StreamingMessage? _currentMessage;
  WorkflowState? _currentWorkflow;
  http.Client? _client;
  String? _currentChatId;
  
  // Track discovered paths during path discovery phase
  final List<List<String>> _discoveredPaths = [];
  bool _pathDiscoveryActive = false;
  List<List<String>>? _lastPathDiscovery; // Store last emitted paths for late subscribers
  
  // Track executor state
  final List<ConsoleEntry> _consoleEntries = [];
  String? _currentExecutingTool;
  int? _currentStepIndex;
  final Map<String, String> _stepWorkspaceDirs = {}; // tool_name -> workspace_dir
  
  // Execution progress tracking (for progress bar in ChatPanel)
  int _completedToolCount = 0;
  int _totalToolCount = 0;
  
  // Track node iteration counts for loop detection
  final Map<String, int> _nodeIterationCounts = {}; // node_name -> count
  
  /// Start streaming a message to the chat with optional file attachments  
  Future<void> sendMessage(String chatId, String message, {List<FileAttachment>? attachments, bool interrupted = false}) async {
    try {
      // Starting stream for chat
      _currentChatId = chatId;
      _client = http.Client();
      final url = AppConfig.api('/messages/$chatId');
      
      http.StreamedResponse response;
      
      if (attachments != null && attachments.isNotEmpty) {
        // Create multipart request for files + message
        final request = http.MultipartRequest('POST', url)
          ..headers.addAll({
            'Accept': 'application/x-ndjson',
          })
          ..fields['message'] = message
          ..fields['interrupted'] = interrupted.toString();
        
        // Add files to the request
        for (final attachment in attachments) {
          if (attachment.path != null) {
            final multipartFile = await http.MultipartFile.fromPath(
              'files',
              attachment.path!,
            );
            request.files.add(multipartFile);
          }
        }
        
        response = await _client!.send(request);
      } else {
        // Create simple form request for message only
        final request = http.Request('POST', url)
          ..headers.addAll({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/x-ndjson',
          })
          ..body = 'message=${Uri.encodeComponent(message)}&interrupted=${interrupted.toString()}';
        
        response = await _client!.send(request);
      }

      if (response.statusCode != 200) {
        throw Exception('Failed to send message: ${response.statusCode}');
      }

      // Initialize streaming message
      _currentMessage = StreamingMessage(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        role: 'assistant',
        content: '',
      );
      
      // Initialize empty workflow
      _currentWorkflow = WorkflowState(
        sections: <String, WorkflowSection>{},
        sectionOrder: <String>[],
      );
      
      // Initialize path discovery state
      _discoveredPaths.clear();
      _pathDiscoveryActive = true;
      _lastPathDiscovery = null;
      
      // Initialize executor state
      _consoleEntries.clear();
      _currentExecutingTool = null;
      _currentStepIndex = null;
      _stepWorkspaceDirs.clear();
      
      // Reset execution progress
      _completedToolCount = 0;
      _totalToolCount = 0;
      
      // Initialize node iteration tracking
      _nodeIterationCounts.clear();

      // Process streaming response
      await for (final chunk in response.stream.transform(utf8.decoder).transform(const LineSplitter())) {
        if (chunk.trim().isEmpty) continue;
        
        try {
          final json = jsonDecode(chunk) as Map<String, dynamic>;
          final event = StreamEvent.fromJson(json);
          
          // Emit raw event
          _eventController.add(event);
          
          // Process specific event types
          await _processEvent(event);
        } catch (e) {
          _eventController.addError('Error parsing chunk: $e');
        }
      }
    } catch (e) {
      _eventController.addError(e);
      rethrow;
    } finally {
      _client?.close();
      _client = null;
    }
  }

  /// Process individual streaming events
  Future<void> _processEvent(StreamEvent event) async {
    switch (event.type) {
      case StreamEventType.updates:
        await _handleUpdateEvent(event);
        break;
      case StreamEventType.messages:
        await _handleMessageEvent(event);
        break;
      case StreamEventType.custom:
        await _handleCustomEvent(event);
        break;
      case StreamEventType.persisted:
        await _handlePersistedEvent(event);
        break;
      case StreamEventType.error:
        await _handleErrorEvent(event);
        break;
    }
  }

  /// Handle state update events (orchestrator workflow steps)
  Future<void> _handleUpdateEvent(StreamEvent event) async {
    final data = event.data;
    
    debugPrint('🔄 [UPDATE EVENT] Received data: ${data.runtimeType}');
    
    // Ensure data is a Map before processing
    if (data is! Map<String, dynamic>) {
      debugPrint('⚠️ [UPDATE EVENT] Data is not Map<String, dynamic>, skipping');
      return;
    }
    
    debugPrint('🔄 [UPDATE EVENT] Processing ${data.keys.length} nodes: ${data.keys.join(", ")}');
    
    // Extract the actual state update from the nested structure with safe casting
    // The data contains keys like "precedent", "classify", "route", etc.
    try {
      bool workflowUpdated = false;
      final updatedSections = Map<String, WorkflowSection>.from(_currentWorkflow?.sections ?? {});
      final currentOrder = List<String>.from(_currentWorkflow?.sectionOrder ?? []);
      
      for (final entry in data.entries) {
        final nodeKey = entry.key;
        debugPrint('🔄 [UPDATE EVENT] Processing node: $nodeKey');
        
        // Safe casting - entry.value might be Map, List, String, etc.
        Map<String, dynamic> nodeData = {};
        if (entry.value is Map<String, dynamic>) {
          nodeData = entry.value as Map<String, dynamic>;
        } else if (entry.value is Map) {
          // Try to convert generic Map to typed Map
          try {
            nodeData = Map<String, dynamic>.from(entry.value as Map);
          } catch (e) {
            // Skip this entry if conversion fails
            continue;
          }
        } else {
          // Skip non-map values
          continue;
        }
        
        // Extract next_node to determine which section to create/show next
        final nextNode = nodeData['next_node']?.toString();
        debugPrint('🔄 [UPDATE EVENT] node=$nodeKey, next_node=$nextNode');
        
        // Extract reasoning content
        String reasoningContent = '';
        if (nodeData.containsKey('${nodeKey}_reasoning')) {
          reasoningContent = nodeData['${nodeKey}_reasoning']?.toString() ?? '';
        }
        
        // Extract clarification if available
        String? clarification;
        if (nodeData.containsKey('${nodeKey}_clarification')) {
          clarification = nodeData['${nodeKey}_clarification']?.toString();
        }
        
        // Update the CURRENT node's section (mark it as complete, will get thinkingTime from CUSTOM event)
        final existing = updatedSections[nodeKey];
        if (existing != null) {
          // Update existing section
          final updatedReasoning = existing.reasoningContent.isEmpty 
              ? reasoningContent 
              : (reasoningContent.isNotEmpty 
                  ? '${existing.reasoningContent}\n\n$reasoningContent'
                  : existing.reasoningContent);
          
          updatedSections[nodeKey] = existing.copyWith(
            reasoningContent: updatedReasoning,
            clarification: clarification ?? existing.clarification,
            status: 'done', // Mark as done when UPDATE event arrives
            isThinking: false,
            isAutoExpanded: false, // Collapse when moving to next section
          );
          debugPrint('📝 TITLE: Marked "$nodeKey" as done and collapsed');
        } else {
          // Create section for current node if it doesn't exist (shouldn't normally happen)
          final title = _nodeTitles[nodeKey] ?? nodeKey;
          updatedSections[nodeKey] = WorkflowSection(
            node: nodeKey,
            title: title,
            status: 'done',
            reasoningContent: reasoningContent,
            thinkingTime: null,
            isThinking: false,
            clarification: clarification,
            isAutoExpanded: false, // Start collapsed if created late
          );
          if (!currentOrder.contains(nodeKey)) {
            currentOrder.add(nodeKey);
          }
          debugPrint('📝 TITLE: Created and marked "$nodeKey" as done and collapsed');
        }
        
        // Create/prepare the NEXT node's section based on next_node
        if (nextNode != null && nextNode != 'END' && nextNode.isNotEmpty) {
          // Check if this is a loop (next_node already has a completed section with thinkingTime)
          final nextNodeExisting = updatedSections[nextNode];
          String nextSectionKey = nextNode;
          
          if (nextNodeExisting != null && nextNodeExisting.thinkingTime != null && nextNodeExisting.thinkingTime! > 0) {
            // This is a loop - next_node was already completed, create iteration
            final iterationCount = _nodeIterationCounts[nextNode] ?? 1;
            _nodeIterationCounts[nextNode] = iterationCount + 1;
            nextSectionKey = '${nextNode}_${iterationCount + 1}';
            debugPrint('🔁 TITLE: Loop to "$nextNode" - creating iteration "${nextSectionKey}"');
          } else {
            // First time for this next_node
            _nodeIterationCounts[nextNode] = 1;
            debugPrint('✨ TITLE: Preparing next section "${nextSectionKey}"');
          }
          
          // Create or update the next section
          final nextTitle = _nodeTitles[nextNode] ?? nextNode;
          final nextExisting = updatedSections[nextSectionKey];
          
          if (nextExisting == null) {
            // Create new section for next node - start expanded
            updatedSections[nextSectionKey] = WorkflowSection(
              node: nextNode,
              title: nextTitle,
              status: 'pending',
              reasoningContent: '',
              thinkingTime: null,
              isThinking: false,
              isAutoExpanded: true, // Auto-expand the new section
            );
            
            // Add to order
            if (!currentOrder.contains(nextSectionKey)) {
              currentOrder.add(nextSectionKey);
            }
            
            debugPrint('📝 TITLE: Created next section "${nextSectionKey}" with title "${nextTitle}" (expanded)');
          }
        }
        
        workflowUpdated = true;
        
        // Special handling for precedent → route (match found, skipping classify + find_path)
        if (nodeKey == 'precedent' && nextNode == 'route') {
          // 1. Set chat title from objective
          final objective = nodeData['objective']?.toString() ?? '';
          if (objective.trim().isNotEmpty && _currentChatId != null) {
            _chatTitleController.add(objective.trim());
            debugPrint('📋 PRECEDENT: Set chat title to "$objective"');
          }
          
          // 2. Emit path discovery data (for graph visualization)
          if (nodeData.containsKey('all_paths')) {
            final allPathsData = nodeData['all_paths'];
            
            if (allPathsData is List && allPathsData.isNotEmpty) {
              // Extract tool names from path metadata (same format as find_path)
              final List<List<String>> allPaths = [];
              for (int i = 0; i < allPathsData.length; i++) {
                final pathData = allPathsData[i];
                if (pathData is List) {
                  // Extract tool names (pure path, no endpoints)
                  final List<String> toolNames = [];
                  for (final tool in pathData) {
                    if (tool is Map<String, dynamic>) {
                      final name = tool['name']?.toString();
                      if (name != null) toolNames.add(name);
                    }
                  }
                  
                  // Only add path if it has tools
                  if (toolNames.isNotEmpty) {
                    allPaths.add(toolNames);
                    debugPrint('🎯 PRECEDENT: Path ${i + 1}: ${toolNames.join(' -> ')}');
                  }
                }
              }
              
              // Emit to pathDiscovery stream to trigger execution panel and graph
              if (allPaths.isNotEmpty) {
                _pathDiscoveryController.add(allPaths);
                _pathDiscoveryActive = true;
                
                // Store for late subscribers
                _lastPathDiscovery = allPaths;
                
                debugPrint('🎯 PRECEDENT: Emitted ${allPaths.length} path(s) from precedent');
              }
            }
          }
        }
        
        // Check for objective update to set chat title (for standard classify flow)
        if (nodeKey == 'classify' && nodeData.containsKey('objective') && _currentChatId != null) {
          final objective = nodeData['objective']?.toString() ?? '';
          if (objective.trim().isNotEmpty) {
            _chatTitleController.add(objective.trim());
          }
        }
        
        // Check if find_path is complete
        if (nodeKey == 'find_path' && nodeData.containsKey('all_paths')) {
          // Keep _pathDiscoveryActive true until route completes
          
          // Extract all paths if available (emit pure tool lists, no endpoints)
          final allPathsData = nodeData['all_paths'];
          if (allPathsData is List && allPathsData.isNotEmpty) {
            final List<List<String>> allPaths = [];
            for (int i = 0; i < allPathsData.length; i++) {
              final pathData = allPathsData[i];
              if (pathData is List) {
                // Extract tool names (pure path, no endpoints)
                final List<String> toolNames = [];
                for (final tool in pathData) {
                  if (tool is Map<String, dynamic>) {
                    final name = tool['name']?.toString();
                    if (name != null) toolNames.add(name);
                  }
                }
                
                // Only add path if it has tools
                if (toolNames.isNotEmpty) {
                  allPaths.add(toolNames);
                  debugPrint('🛤️ [UPDATE EVENT] Path ${i + 1}: ${toolNames.join(' -> ')}');
                }
              }
            }
            
            // Only emit if there are valid paths
            if (allPaths.isNotEmpty) {
              _lastPathDiscovery = allPaths;
              _pathDiscoveryController.add(allPaths);
              debugPrint('📋 [UPDATE EVENT] FINAL PATHS EMITTED: ${allPaths.length} total paths');
            }
          }
        }
        
        // Check if route stage has chosen a path
        if (nodeKey == 'route' && nodeData.containsKey('chosen_path')) {
          debugPrint('🎯 [UPDATE EVENT] ROUTE has chosen_path');
          debugPrint('📊 [UPDATE EVENT] chosen_path data type: ${nodeData['chosen_path'].runtimeType}');
          // Stop path discovery now that route has chosen a path
          _pathDiscoveryActive = false;
          final chosenPathData = nodeData['chosen_path'];
          if (chosenPathData is List) {
            debugPrint('📊 [UPDATE EVENT] chosen_path contains ${chosenPathData.length} tools');
            
            // Extract tool names first
            final List<String> toolNames = [];
            for (int i = 0; i < chosenPathData.length; i++) {
              final tool = chosenPathData[i];
              if (tool is Map<String, dynamic>) {
                final name = tool['name']?.toString();
                if (name != null) {
                  toolNames.add(name);
                  debugPrint('  🔧 [UPDATE EVENT] Tool ${i + 1}: $name');
                }
              }
            }
            
            // Only emit if there are actual tools
            if (toolNames.isNotEmpty) {
              // Emit path as-is (just tools, no endpoints)
              _chosenPathController.add(toolNames);
              debugPrint('🎯 [UPDATE EVENT] CHOSEN PATH EMITTED: ${toolNames.join(' -> ')}');
              
              // Initialize total tool count
              _totalToolCount = toolNames.length;
              _completedToolCount = 0;
              
              // Emit initial progress update so ChatPanel shows bar at 0%
              _executionProgressController.add({
                'completed': _completedToolCount,
                'total': _totalToolCount,
              });
            } else {
              debugPrint('⚠️ [UPDATE EVENT] Chosen path has no tools, not emitting');
            }
          }
        }
        
        // Update current message state
        if (_currentMessage != null) {
          _currentMessage = _currentMessage!.copyWith(
            state: {..._currentMessage!.state ?? {}, ...nodeData},
          );
        }
      } // End of for loop
      
      // Update workflow state if changed
      if (workflowUpdated) {
        _currentWorkflow = WorkflowState(
          sections: updatedSections,
          sectionOrder: currentOrder,
        );
        
        // Update message with workflow
        if (_currentMessage != null) {
          _currentMessage = _currentMessage!.copyWith(
            workflow: _currentWorkflow,
          );
        }
        
        _workflowController.add(_currentWorkflow!);
      }
    } catch (e) {
      _eventController.addError('Update parsing error: $e');
    }
  }

  /// Handle LLM message streaming events
  Future<void> _handleMessageEvent(StreamEvent event) async {
    final data = event.data;
    
    String messageContent = '';
    String reasoningContent = '';
    String? langgraphNode;
    
    // Handle different data formats with better error handling
    try {
      if (data is List && data.isNotEmpty) {
        // Handle tuple format: [AIMessageChunk, metadata]
        final messageChunk = data[0];
        if (messageChunk is Map<String, dynamic>) {
          messageContent = messageChunk['content']?.toString() ?? '';
          
          // Safe handling of additional_kwargs - could be Map, List, or null
          final additionalKwargsRaw = messageChunk['additional_kwargs'];
          if (additionalKwargsRaw is Map<String, dynamic>) {
            reasoningContent = additionalKwargsRaw['reasoning_content']?.toString() ?? '';
          }
        }
        
        // Extract langgraph_node from metadata (data[1])
        if (data.length > 1 && data[1] is Map<String, dynamic>) {
          final metadata = data[1] as Map<String, dynamic>;
          langgraphNode = metadata['langgraph_node']?.toString();
        }
      } else if (data is Map<String, dynamic>) {
        // Handle direct Map structure
        messageContent = data['content']?.toString() ?? '';
        
        // Safe handling of additional_kwargs
        final additionalKwargsRaw = data['additional_kwargs'];
        if (additionalKwargsRaw is Map<String, dynamic>) {
          reasoningContent = additionalKwargsRaw['reasoning_content']?.toString() ?? '';
        }
        
        // Try to extract langgraph_node from direct map
        langgraphNode = data['langgraph_node']?.toString();
      } else if (data is String) {
        // Fallback: parse string representation
        final contentMatch = RegExp(r"content='([^']*)'").firstMatch(data);
        if (contentMatch != null) {
          messageContent = contentMatch.group(1) ?? '';
        }
        
        final reasoningMatch = RegExp(r"'reasoning_content':\s*'([^']*)'").firstMatch(data);
        if (reasoningMatch != null) {
          reasoningContent = reasoningMatch.group(1) ?? '';
        }
        
        // Extract langgraph_node from string
        final nodeMatch = RegExp(r"'langgraph_node':\s*'([^']*)'").firstMatch(data);
        if (nodeMatch != null) {
          langgraphNode = nodeMatch.group(1);
        }
      }
    } catch (e) {
      _eventController.addError('Message parsing error: $e');
    }
    
    // Update current message content
    if (_currentMessage != null) {
      _currentMessage = _currentMessage!.copyWith(
        content: _currentMessage!.content + messageContent,
      );
      
      _messageController.add(_currentMessage!);
    }
    
    // Collapse all reasoning sections when actual content starts streaming
    if (messageContent.isNotEmpty && _currentWorkflow != null) {
      final sections = Map<String, WorkflowSection>.from(_currentWorkflow!.sections);
      bool hasAutoExpandedSections = sections.values.any((section) => section.isAutoExpanded);
      
      if (hasAutoExpandedSections) {
        // Collapse all auto-expanded sections
        final collapsedSections = <String, WorkflowSection>{};
        for (final entry in sections.entries) {
          collapsedSections[entry.key] = entry.value.copyWith(
            isAutoExpanded: false,
          );
        }
        
        _currentWorkflow = _currentWorkflow!.copyWith(sections: collapsedSections);
        _workflowController.add(_currentWorkflow!);
      }
    }
    
    // Handle real-time reasoning streaming
    if (reasoningContent.isNotEmpty && langgraphNode != null) {
      // Initialize workflow if not exists
      _currentWorkflow ??= WorkflowState(sections: {}, sectionOrder: []);
      
      var sections = Map<String, WorkflowSection>.from(_currentWorkflow!.sections);
      final order = List<String>.from(_currentWorkflow!.sectionOrder);
      
      // Get non-null node name for processing
      final nodeKey = langgraphNode;
      
      // Find the most recent section for this node (handling iterations)
      final existingKeys = sections.keys.where((k) => k.startsWith(nodeKey)).toList();
      String sectionKey = nodeKey;
      
      if (existingKeys.isNotEmpty) {
        // Use the most recent iteration
        sectionKey = existingKeys.last;
      }
      
      // Get or create the section for this node
      WorkflowSection? existingSection = sections[sectionKey];
      
      // Collapse all other sections and expand only the current one
      final updatedSections = <String, WorkflowSection>{};
      for (final entry in sections.entries) {
        updatedSections[entry.key] = entry.value.copyWith(
          isAutoExpanded: false, // Collapse all others
        );
      }
      
      if (existingSection == null) {
        // Create new section for this node (shouldn't happen if UPDATE event already created it)
        final title = _nodeTitles[nodeKey] ?? _formatNodeTitle(nodeKey);
        
        existingSection = WorkflowSection(
          node: nodeKey,
          title: title,
          status: 'thinking',
          reasoningContent: reasoningContent,
          isThinking: true,
          isAutoExpanded: true, // Auto-expand the active reasoning section
        );
        
        // Add to order if not already present
        if (!order.contains(sectionKey)) {
          order.add(sectionKey); // Just append, order should be managed by UPDATE events
        }
      } else {
        // Update existing section with new reasoning content
        existingSection = existingSection.copyWith(
          reasoningContent: existingSection.reasoningContent + reasoningContent,
          isThinking: true,
          status: 'thinking',
          isAutoExpanded: true, // Keep the current section expanded
        );
      }
      
      updatedSections[sectionKey] = existingSection;
      sections = updatedSections;
      
      _currentWorkflow = _currentWorkflow!.copyWith(
        sections: sections,
        sectionOrder: order,
      );
      
      // Update message with workflow
      if (_currentMessage != null) {
        _currentMessage = _currentMessage!.copyWith(
          workflow: _currentWorkflow,
        );
      }
      
      _workflowController.add(_currentWorkflow!);
    }
  }

  /// Handle custom events (including thinking time updates, path discoveries, and executor events)
  Future<void> _handleCustomEvent(StreamEvent event) async {
    final data = event.data;
    
    debugPrint('⚙️ [CUSTOM EVENT] Received data type: ${data.runtimeType}');
    
    try {
      if (data is Map<String, dynamic>) {
        debugPrint('⚙️ [CUSTOM EVENT] Data keys: ${data.keys.join(", ")}');
        
        // Handle executor events (tool execution)
        final toolName = data['tool_name']?.toString();
        final status = data['status']?.toString();
        final stdout = data['stdout']?.toString();
        final workspaceDir = data['workspace_dir']?.toString();
        
        // Executor event: Tool execution start
        if (toolName != null && status == 'start' && workspaceDir != null) {
          debugPrint('🔧 [CUSTOM EVENT] EXECUTOR START: $toolName at $workspaceDir');
          
          // Calculate step index from chosen path (1-based for file naming)
          int stepIndex = 0;
          final chosenPath = _currentMessage?.state?['chosen_path'] as List?;
          debugPrint('🔧 [CUSTOM EVENT] Chosen path for step calc: $chosenPath');
          if (chosenPath != null) {
            for (int i = 0; i < chosenPath.length; i++) {
              final step = chosenPath[i];
              final stepName = step is Map ? step['name']?.toString() : step.toString();
              if (stepName == toolName) {
                stepIndex = i + 1; // 1-based indexing for output files (01_tool, 02_tool, etc.)
                debugPrint('🔧 [CUSTOM EVENT] Found $toolName at index $i, using stepIndex $stepIndex');
                break;
              }
            }
          }
          
          _currentExecutingTool = toolName;
          _currentStepIndex = stepIndex;
          _stepWorkspaceDirs[toolName] = workspaceDir;
          
          debugPrint('🔧 [CUSTOM EVENT] Set _currentStepIndex=$stepIndex, _currentExecutingTool=$toolName');
          
          // Update workflow to show "Executing..." section
          if (_currentWorkflow != null && !_currentWorkflow!.sections.containsKey('execute')) {
            final updatedSections = Map<String, WorkflowSection>.from(_currentWorkflow!.sections);
            final updatedOrder = List<String>.from(_currentWorkflow!.sectionOrder);
            
            // Add execute section if not present
            updatedSections['execute'] = WorkflowSection(
              node: 'execute',
              title: 'Executing...',
              status: 'in_progress',
              reasoningContent: '',
              thinkingTime: 0.0,
              isThinking: false,
            );
            
            // Add to order after route
            if (!updatedOrder.contains('execute')) {
              final routeIndex = updatedOrder.indexOf('route');
              if (routeIndex >= 0) {
                updatedOrder.insert(routeIndex + 1, 'execute');
              } else {
                updatedOrder.add('execute');
              }
            }
            
            _currentWorkflow = WorkflowState(
              sections: updatedSections,
              sectionOrder: updatedOrder,
            );
            
            _workflowController.add(_currentWorkflow!);
            debugPrint('🔧 [CUSTOM EVENT] Added "Executing..." section to workflow');
          }
          
          // Emit tool change
          _currentToolController.add(toolName);
          debugPrint('🔧 [CUSTOM EVENT] Emitted tool change: $toolName');
          
          // Emit executor step data
          _executorStepController.add(ExecutorStepData(
            toolName: toolName,
            stepIndex: stepIndex,
            workspaceDir: workspaceDir,
            status: 'start',
          ));
          debugPrint('🔧 [CUSTOM EVENT] Emitted executor step data (start)');
        }
        
        // Executor event: Console output (stdout)
        else if (toolName != null && stdout != null) {
          final timestamp = DateTime.now().toIso8601String();
          final entry = ConsoleEntry(
            timestamp: timestamp,
            type: 'stdout',
            line: stdout,
            stepIndex: _currentStepIndex,
            toolName: toolName,
          );
          
          _consoleEntries.add(entry);
          _consoleController.add(entry);
        }
        
        // Executor event: Tool execution end
        else if (toolName != null && status == 'end') {
          debugPrint('✅ [CUSTOM EVENT] EXECUTOR END: $toolName');
          
          final stepIndex = _currentStepIndex ?? 0;
          final workspaceDir = _stepWorkspaceDirs[toolName];
          
          debugPrint('✅ [CUSTOM EVENT] Step $stepIndex completed, workspace: $workspaceDir');
          
          // Clear current executing tool
          _currentExecutingTool = null;
          
          // Increment completed tool count
          _completedToolCount++;
          
          // Emit progress update
          _executionProgressController.add({
            'completed': _completedToolCount,
            'total': _totalToolCount,
          });
          
          // Emit executor step completion
          _executorStepController.add(ExecutorStepData(
            toolName: toolName,
            stepIndex: stepIndex,
            workspaceDir: workspaceDir,
            status: 'end',
          ));
          debugPrint('✅ [CUSTOM EVENT] Emitted executor step data (end)');
        }
        
        // Check if this is a path discovery event
        final pathData = data['path'];
        if (pathData != null && pathData is List) {
          debugPrint('🛤️ PATH DISCOVERY: Found ${pathData.length} tools in path');
          
          // Extract tool names from PathToolMetadata
          final List<String> toolNames = [];
          for (final tool in pathData) {
            if (tool is Map<String, dynamic>) {
              final name = tool['name']?.toString();
              if (name != null) {
                toolNames.add(name);
              }
            } else if (tool.toString().contains('name=')) {
              // Parse from string representation: "PathToolMetadata(name='image_ocr', ..."
              final nameMatch = RegExp(r"name='([^']*)'").firstMatch(tool.toString());
              if (nameMatch != null) {
                toolNames.add(nameMatch.group(1)!);
              }
            }
          }
          
          if (toolNames.isNotEmpty && _pathDiscoveryActive) {
            // Store path as-is (just tools, no endpoints)
            // Check for duplicates
            final pathString = toolNames.join('->');
            final isDuplicate = _discoveredPaths.any((path) => path.join('->') == pathString);
            
            if (!isDuplicate) {
              _discoveredPaths.add(toolNames);
              
              // Emit updated paths list
              _lastPathDiscovery = List.from(_discoveredPaths);
              _pathDiscoveryController.add(_lastPathDiscovery!);
            }
          }
        }
        
        // Check if this is a thinking time event
        final node = data['node']?.toString();
        final thinkDuration = data['think_duration'];
        
        if (node != null && thinkDuration != null && _currentWorkflow != null) {
          // Convert nanoseconds to seconds
          double thinkingTimeSeconds = 0.0;
          if (thinkDuration is int) {
            thinkingTimeSeconds = thinkDuration / 1000000000.0;
          } else if (thinkDuration is double) {
            thinkingTimeSeconds = thinkDuration / 1000000000.0;
          }
          
          debugPrint('⏱️ THINKING TIME: node=$node, time=${thinkingTimeSeconds}s');
          
          // Find the most recent section for this node (handling iterations)
          final sections = Map<String, WorkflowSection>.from(_currentWorkflow!.sections);
          final matchingKeys = sections.keys.where((k) => k.startsWith(node)).toList();
          
          if (matchingKeys.isNotEmpty) {
            // Use the most recent iteration
            final sectionKey = matchingKeys.last;
            final existingSection = sections[sectionKey];
            
            if (existingSection != null) {
              sections[sectionKey] = existingSection.copyWith(
                thinkingTime: thinkingTimeSeconds,
                isThinking: false, // No longer thinking, now shows time
                status: 'completed',
                isAutoExpanded: false, // Collapse this section when completed
              );
              
              _currentWorkflow = _currentWorkflow!.copyWith(sections: sections);
              
              // Update message with workflow
              if (_currentMessage != null) {
                _currentMessage = _currentMessage!.copyWith(
                  workflow: _currentWorkflow,
                );
              }
              
              _workflowController.add(_currentWorkflow!);
              debugPrint('⏱️ THINKING TIME: Updated section "$sectionKey" with time');
            }
          }
        }
      }
    } catch (e) {
      debugPrint('❌ CUSTOM EVENT PARSE ERROR: $e');
      debugPrint('🔍 CUSTOM DATA: $data');
    }
  }
  
  /// Format node name to friendly title
  String _formatNodeTitle(String node) {
    switch (node) {
      case 'precedent':
        return 'Searching for precedent...';
      case 'classify':
        return 'Classifying...';
      case 'find_path':
        return 'Searching for possible paths...';
      case 'route':
        return 'Selecting the path...';
      case 'execute':
        return 'Executing...';
      case 'finalize':
        return 'Formatting response...';
      default:
        // Convert snake_case to Title Case
        return '${node.split('_')
            .map((word) => word.isEmpty ? word : word[0].toUpperCase() + word.substring(1))
            .join(' ')}...';
    }
  }

  /// Handle persisted event (final message IDs)
  Future<void> _handlePersistedEvent(StreamEvent event) async {
    final data = event.data;
    
    // Ensure data is a Map before processing
    if (data is! Map<String, dynamic>) {
      return;
    }
    
    // Complete workflow sections first
    if (_currentWorkflow != null) {
      final updatedSections = <String, WorkflowSection>{};
      
      for (final entry in _currentWorkflow!.sections.entries) {
        updatedSections[entry.key] = entry.value.copyWith(
          isThinking: false,
          isAutoExpanded: false, // Ensure all sections are collapsed when persisted
        );
      }
      
      _currentWorkflow = _currentWorkflow!.copyWith(
        sections: updatedSections,
      );
      
      _workflowController.add(_currentWorkflow!);
      debugPrint('✅ PERSISTED: Completed workflow with ${_currentWorkflow!.sections.length} sections');
    }
    
    // Complete the current message WITH the workflow attached
    if (_currentMessage != null) {
      _currentMessage = _currentMessage!.copyWith(
        id: data['assistant_message_id']?.toString() ?? _currentMessage!.id,
        workflow: _currentWorkflow, // Attach the completed workflow
        isPersisted: true, // Mark as final persisted message
        type: data['message_type']?.toString(), // Include message type for interrupt detection
      );
      
      _messageController.add(_currentMessage!);
      debugPrint('✅ PERSISTED: Completed message with workflow attached, isPersisted=true, type=${_currentMessage!.type}');
    }
  }

  /// Handle error events
  Future<void> _handleErrorEvent(StreamEvent event) async {
    final data = event.data;
    String errorMessage = 'Unknown error';
    
    if (data is Map<String, dynamic> && data.containsKey('message')) {
      errorMessage = data['message']?.toString() ?? 'Unknown error';
    } else if (data is String) {
      errorMessage = data;
    }
    
    _eventController.addError(Exception(errorMessage));
  }

  /// Get current console entries (for accessing accumulated console output)
  List<ConsoleEntry> get currentConsoleEntries => List.unmodifiable(_consoleEntries);
  
  /// Get current executing tool name
  String? get currentExecutingTool => _currentExecutingTool;
  
  /// Get current step index
  int? get currentStepIndex => _currentStepIndex;
  
  /// Get workspace directory for a specific tool
  String? getWorkspaceDir(String toolName) => _stepWorkspaceDirs[toolName];
  
  /// Cancel current streaming operation
  void cancel() {
    _client?.close();
    _client = null;
  }

  /// Dispose of the service
  void dispose() {
    cancel();
    _eventController.close();
    _messageController.close();
    _workflowController.close();
    _chatTitleController.close();
    _pathDiscoveryController.close();
    _chosenPathController.close();
    _consoleController.close();
    _executorStepController.close();
    _currentToolController.close();
    _executionProgressController.close();
  }
}

