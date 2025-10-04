import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:gui/data/models/file_attachment.dart';
import 'package:gui/data/services/chat_service.dart';
import 'package:gui/data/services/streaming_service.dart';
import 'package:gui/widgets/chat/chat_input.dart';
import 'package:gui/widgets/chat/chat_message.dart';
import 'package:gui/widgets/chat/drag_drop_handler.dart';
import 'package:gui/widgets/chat/message_reasoning.dart';
import 'package:gui/widgets/chat/summary_card.dart';

class ChatPanel extends StatefulWidget {
  final String? chatId;
  final Function(String)? onTitleUpdated;
  final StreamingService? streamingService;
  final Function(int messageId, Map<String, dynamic> stateData)? onExecutionSelected;
  final VoidCallback? onMessageSent;

  const ChatPanel({
    super.key, 
    required this.chatId,
    this.onTitleUpdated,
    this.streamingService,
    this.onExecutionSelected,
    this.onMessageSent,
  });

  @override
  State<ChatPanel> createState() => _ChatPanelState();
}

class _ChatPanelState extends State<ChatPanel> {
  final ChatService _service = const ChatService();
  late StreamingService _streamingService;
  final ScrollController _scrollController = ScrollController();
  final GlobalKey<ChatInputState> _chatInputKey = GlobalKey<ChatInputState>();
  bool _loading = false;
  String? _error;
  List<Map<String, dynamic>> _messages = <Map<String, dynamic>>[];
  final TextEditingController _controller = TextEditingController();
  bool _sending = false;
  
  // Streaming state
  StreamingMessage? _currentStreamingMessage;
  WorkflowState? _currentWorkflow;
  
  // Execution progress state
  int _completedTools = 0;
  int _totalTools = 0;
  bool _showProgressBar = false;
  
  // Stream subscriptions
  StreamSubscription<Map<String, int>>? _progressSubscription;
  StreamSubscription<StreamingMessage>? _messageStreamSubscription;

  @override
  void initState() {
    super.initState();
    _streamingService = widget.streamingService ?? StreamingService();
    debugPrint('💬 CHAT PANEL INITIALIZED - chatId: ${widget.chatId}');
    _setupStreamingListeners();
    if (widget.chatId != null) {
      _fetch();
    }
  }

  void _setupStreamingListeners() {
    // Cancel previous subscriptions to avoid duplicates
    _progressSubscription?.cancel();
    _messageStreamSubscription?.cancel();
    
    // Listen to execution progress updates
    _progressSubscription = _streamingService.executionProgress.listen((progress) {
      if (mounted) {
        setState(() {
          _completedTools = progress['completed'] ?? 0;
          _totalTools = progress['total'] ?? 0;
          // Show progress bar during execution and keep it visible during finalization
          _showProgressBar = _totalTools > 0;
        });
      }
    });
    
    // Listen to streaming messages
    _messageStreamSubscription = _streamingService.messages.listen((streamingMessage) {
      
      // Only add to permanent messages when it's actually persisted (not just streaming updates)
      if (streamingMessage.isPersisted) {
        // This is the final persisted message with workflow attached - add it to permanent messages
        final assistantMessage = <String, dynamic>{
          'role': 'assistant',
          'content': streamingMessage.content,
          'timestamp': DateTime.now().toIso8601String(),
          'id': streamingMessage.id,
          'type': streamingMessage.type ?? 'response', // Include type for interrupt detection
        };
        
        // Check if this message should have a summary card
        // Summary card is shown if workflow reached find_path/route stage (has all_paths or chosen_path)
        bool shouldHaveSummaryCard = false;
        
        // Add workflow data if present (for stored reasoning display)
        if (streamingMessage.workflow != null) {
          // Convert workflow to stored format that _parseStoredReasoning expects
          final workflowSections = <Map<String, dynamic>>[];
          for (final section in streamingMessage.workflow!.sections.values) {
            workflowSections.add({
              'node': section.node,
              'content': section.reasoningContent,
              'think_duration': (section.thinkingTime ?? 0.0) * 1000000000.0, // Convert back to nanoseconds
            });
            
              // Check if workflow includes find_path or route node (indicates path discovery happened)
              if (section.node == 'find_path' || section.node == 'route') {
                shouldHaveSummaryCard = true;
              }
            }
            assistantMessage['reasoning'] = {'content': workflowSections};
            debugPrint('📋 FINAL MESSAGE: Added workflow with ${workflowSections.length} sections, type=${assistantMessage['type']}');
          }
          
          // Mark message as having state if it should show summary card
          if (shouldHaveSummaryCard) {
            assistantMessage['has_state'] = true;
            debugPrint('📊 FINAL MESSAGE: Marked as has_state=true for summary card');
          }
          
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              setState(() {
                _messages.add(assistantMessage); // Add to end for chronological order with reverse: false
                _currentStreamingMessage = null;
                _currentWorkflow = null;
                _sending = false;
              });
              _scrollToBottom();
            }
          });
          
          debugPrint('📋 FINAL MESSAGE: Added to permanent list, will stop calling _parseStoredReasoning repeatedly');
        } else {
          // This is a streaming update - update current streaming message display only
          if (mounted) {
            setState(() {
              _currentStreamingMessage = streamingMessage;
            });
            _scrollToBottom();
          }
        }
      });

    // Listen to workflow updates
    _streamingService.workflow.listen((workflow) {
      if (mounted) {
        setState(() {
          _currentWorkflow = workflow;
        });
      }
    });

    // Listen to chat title updates
    _streamingService.chatTitleUpdates.listen((objective) {
      if (widget.chatId != null) {
        _updateChatTitle(objective);
      }
    });

    // Listen to stream events for error handling
    _streamingService.events.listen(
      (event) {
        // Handle specific event types if needed
      },
      onError: (error) {
        if (mounted) {
          setState(() {
            _error = 'Streaming error: $error';
            _sending = false;
          });
        }
      },
    );
  }

  Future<void> _updateChatTitle(String title) async {
    try {
      debugPrint('🔄 CHAT: Starting title update to: $title');
      await _service.updateChat(widget.chatId!, title: title);
      
      // Notify parent about title change - this triggers the sidebar animation
      widget.onTitleUpdated?.call(title);
      debugPrint('✅ CHAT: Title update completed');
      
    } catch (e) {
      debugPrint('❌ CHAT: Title update failed: $e');
      // Handle error silently - title update is not critical
    }
  }

  /// Parse stored reasoning data from API response into WorkflowState
  WorkflowState? _parseStoredReasoning(dynamic reasoningData) {
    try {
      debugPrint('🔍 PARSING STORED REASONING: ${reasoningData.runtimeType}');
      
      if (reasoningData is! Map<String, dynamic>) {
        debugPrint('❌ REASONING DATA is not Map: ${reasoningData.runtimeType}');
        return null;
      }
      
      final content = reasoningData['content'];
      if (content is! List) {
        debugPrint('❌ REASONING CONTENT is not List: ${content.runtimeType}');
        return null;
      }
      
      final sections = <String, WorkflowSection>{};
      final sectionOrder = <String>[];
      
      for (final item in content) {
        if (item is! Map<String, dynamic>) continue;
        
        final node = item['node']?.toString() ?? '';
        final reasoningContent = item['content']?.toString() ?? '';
        final thinkDuration = item['think_duration'];
        
        if (node.isEmpty) continue;
        
        // Convert think_duration from nanoseconds to seconds
        double? thinkingTime;
        if (thinkDuration is num) {
          thinkingTime = thinkDuration.toDouble() / 1000000000.0; // Convert nanoseconds to seconds
        }
        
        final section = WorkflowSection(
          node: node,
          title: _getNodeTitle(node),
          status: 'completed',
          reasoningContent: reasoningContent,
          thinkingTime: thinkingTime,
          isThinking: false,
          isAutoExpanded: false,
        );
        
        sections[node] = section;
        sectionOrder.add(node);
      }
      
      
      final workflowState = WorkflowState(
        sections: sections,
        sectionOrder: sectionOrder,
      );
      
      return workflowState;
      
    } catch (e) {
      debugPrint('❌ PARSE STORED REASONING ERROR: $e');
      return null;
    }
  }

  String _getNodeTitle(String node) {
    switch (node) {
      case 'classify':
        return 'Classification';
      case 'precedent':
        return 'Precedent Search';
      case 'find_path':
        return 'Path Discovery';
      case 'route':
        return 'Path Selection';
      case 'execute':
        return 'Execution';
      case 'finalize':
        return 'Finalization';
      default:
        return node.split('_').map((word) => word[0].toUpperCase() + word.substring(1)).join(' ');
    }
  }

  @override
  void didUpdateWidget(covariant ChatPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.chatId != widget.chatId) {
      debugPrint('🔄 CHAT PANEL: chatId changed from ${oldWidget.chatId} to ${widget.chatId}');
      if (widget.chatId == null || widget.chatId!.isEmpty) {
        debugPrint('🔄 CHAT PANEL: Clearing chat - showing empty state');
        setState(() {
          _messages = <Map<String, dynamic>>[];
          _currentStreamingMessage = null;
          _currentWorkflow = null;
          _loading = false;
          _error = null;
        });
      } else {
        _fetch();
      }
    }
  }

  Future<void> _fetch() async {
    final chatId = widget.chatId;
    debugPrint('🔍 FETCH CALLED for chatId: $chatId');
    
    if (chatId == null || chatId.isEmpty) {
      debugPrint('❌ FETCH CANCELLED - no chatId');
      setState(() {
        _messages = <Map<String, dynamic>>[];
        _error = null;
        _loading = false;
      });
      return;
    }
    
    setState(() {
      _loading = true;
      _error = null;
    });
    
    try {
      debugPrint('📡 CALLING getChatDetail for chat: $chatId');
      final detail = await _service.getChatDetail(chatId);
      
      debugPrint('✅ CHAT DETAIL RESPONSE: $detail');
      
      final msgs = (detail['messages'] as List?) ?? <dynamic>[];
      _messages = msgs.cast<Map>().map((e) => e.cast<String, dynamic>()).toList().reversed.toList();
      setState(() {
        _loading = false;
      });
      _scrollToBottom();
    } catch (e) {
      debugPrint('❌ FETCH ERROR: $e');
      setState(() {
        _loading = false;
        _error = '$e';
      });
    }
  }

  Future<void> _sendMessage(String message, List<FileAttachment> attachments) async {
    if (message.isEmpty && attachments.isEmpty) return;
    
    final chatId = widget.chatId;
    if (chatId == null) {
      debugPrint('❌ Cannot send message: no chatId');
      return;
    }

    setState(() {
      _sending = true;
      _error = null;
      // Reset execution progress
      _completedTools = 0;
      _totalTools = 0;
      _showProgressBar = false;
    });

    try {
      debugPrint('📤 SENDING MESSAGE: $message with ${attachments.length} attachments');
      debugPrint('🔄 MESSAGES: $_messages');

      // Determine if this is a response to an interrupted workflow
      // Check if the last AI message was a question (type: "question")
      // IMPORTANT: Check BEFORE adding the new user message to _messages
      bool interrupted = false;
      if (_messages.isNotEmpty) {
        final lastAiMessage = _messages.lastWhere(
          (msg) => msg['role'] == 'assistant',
          orElse: () => <String, dynamic>{},
        );
        debugPrint('🔄 LAST AI MESSAGE: $lastAiMessage');
        debugPrint('🔄 LAST AI MESSAGE TYPE: ${lastAiMessage['type']}');
        if (lastAiMessage.isNotEmpty && lastAiMessage['type'] == 'question') {
          interrupted = true;
          debugPrint('🔄 DETECTED INTERRUPTED WORKFLOW (last AI message was a question)');
        }
      }

      // Add user message to UI immediately (after checking interrupted status)
      final userMessage = <String, dynamic>{
        'role': 'user',
        'content': message,
        'timestamp': DateTime.now().toIso8601String(),
        'id': DateTime.now().millisecondsSinceEpoch,
      };
      
      // Add attachment metadata if present
      if (attachments.isNotEmpty) {
        userMessage['attachments'] = attachments.map((a) => a.toJson()).toList();
      }

      setState(() {
        _messages.add(userMessage);
      });
      _scrollToBottom();

      // Notify parent that a message was sent (to clear execution selection)
      // IMPORTANT: Call BEFORE sending to reset execution panel immediately
      widget.onMessageSent?.call();

      // Send message via streaming service
      await _streamingService.sendMessage(
        chatId, 
        message,
        attachments: attachments, // Pass attachments to backend
        interrupted: interrupted,
      );

      // Clear input
      _controller.clear();
      
    } catch (e) {
      debugPrint('❌ SEND MESSAGE ERROR: $e');
      setState(() {
        _error = '$e';
        _sending = false;
      });
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _handleFilesAdded(List<FileAttachment> files) async {
    debugPrint('📎 FILES ADDED: ${files.length} files');
    for (final file in files) {
      debugPrint('📄 FILE: ${file.filename} (${file.mimeType})');
    }
    
    // Update the chat input with the new files
    _chatInputKey.currentState?.addDroppedFiles(files);
  }

  Future<void> _selectExecutionPanel(int messageId) async {
    try {
      final stateData = await _fetchMessageState(messageId);
      if (stateData != null && widget.onExecutionSelected != null) {
        widget.onExecutionSelected!(messageId, stateData);
      }
    } catch (e) {
      debugPrint('❌ Error fetching message state for execution panel: $e');
      // Show error briefly
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to load execution data: $e'),
            backgroundColor: Colors.red.shade600,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    }
  }

  Future<Map<String, dynamic>?> _fetchMessageState(dynamic messageId) async {
    if (messageId == null) return null;
    try {
      final id = messageId is int ? messageId : int.tryParse(messageId.toString());
      if (id == null) return null;
      return await _service.getMessageState(id);
    } catch (e) {
      debugPrint('❌ Error fetching message state: $e');
      return null;
    }
  }

  List<List<String>> _extractAllPaths(Map<String, dynamic> stateData) {
    try {
      // Extract all paths from state data
      final allPaths = stateData['all_paths'];
      if (allPaths == null) {
        debugPrint('❌ ALL_PATHS is null');
        return [];
      }
      if (allPaths is! List) {
        debugPrint('❌ ALL_PATHS is not a List: ${allPaths.runtimeType}');
        return [];
      }
      debugPrint('📋 ALL_PATHS LIST LENGTH: ${allPaths.length}');
      final List<List<String>> result = [];
      for (int i = 0; i < allPaths.length; i++) {
        final pathData = allPaths[i];
        final List<String> path = ['IMAGE_IN'];
        for (int j = 0; j < pathData.length; j++) {
          final tool = pathData[j];
          if (tool is Map && tool.containsKey('name')) {
            final name = tool['name']?.toString();
            if (name != null) {
              path.add(name);
              // Tool added
            } else {
              debugPrint('❌ Tool name is null');
            }
          } else {
            debugPrint('❌ Tool is not a Map with name key: $tool');
          }
        }
        path.add('IMAGE_OUT');
        result.add(path);
      }
      return result;
    } catch (e) {
      debugPrint('❌ Error extracting all_paths: $e');
      debugPrint('❌ Stack trace: ${StackTrace.current}');
      return [];
    }
  }

  List<String>? _extractChosenPath(Map<String, dynamic> stateData) {
    try {
      final chosenPath = stateData['chosen_path'];
      if (chosenPath == null) {
        return null;
      }
      if (chosenPath is! List || chosenPath.isEmpty) {
        return null;
      }
      final List<String> result = ['IMAGE_IN'];
      for (int i = 0; i < chosenPath.length; i++) {
        final tool = chosenPath[i];
        if (tool is Map && tool.containsKey('name')) {
          final name = tool['name']?.toString();
          if (name != null) {
            result.add(name);
          }
        } else {
          debugPrint('❌ Chosen tool parsing failed: ${tool.runtimeType}');
        }
      }
      result.add('IMAGE_OUT');
      
      // If we only have endpoints (no tools in between), treat as no chosen path
      if (result.length <= 2) return null;
      
      return result;
    } catch (e) {
      debugPrint('❌ Error extracting chosen_path: $e');
      debugPrint('❌ Stack trace: ${StackTrace.current}');
      return null;
    }
  }

  Future<bool> _handleSavePrecedent(Map<String, dynamic> message) async {
    try {
      final messageId = message['id'];
      if (messageId == null) return false;
      
      // Parse message_id to int
      final int parsedMessageId = int.parse(messageId.toString());
      
      // Check if already saved - if so, delete instead
      final bool isAlreadySaved = message['precedent_id'] != null;
      
      if (isAlreadySaved) {
        // Delete precedent
        final response = await _service.deletePrecedent(parsedMessageId);
        
        if (response['success'] == true) {
          // Clear the precedent_id from the message
          setState(() {
            final messageIndex = _messages.indexWhere((m) => m['id'] == message['id']);
            if (messageIndex != -1) {
              _messages[messageIndex]['precedent_id'] = null;
            }
          });
          
          // Show success message
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: const Text('Precedent removed successfully'),
                backgroundColor: Colors.orange.shade600,
                duration: const Duration(seconds: 2),
              ),
            );
          }
          
          return true;
        }
      } else {
        // Save precedent
        final response = await _service.savePrecedent(parsedMessageId);
        
        if (response['success'] == true) {
          // Update the message with the precedent_id
          setState(() {
            final messageIndex = _messages.indexWhere((m) => m['id'] == message['id']);
            if (messageIndex != -1) {
              _messages[messageIndex]['precedent_id'] = response['precedent_id'];
            }
          });
          
          // Show success message
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(response['already_exists'] == true 
                    ? 'Workflow already saved as precedent' 
                    : 'Workflow saved as precedent successfully'),
                backgroundColor: Colors.green.shade600,
                duration: const Duration(seconds: 2),
              ),
            );
          }
          
          return true;
        }
      }
      
      return false;
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to toggle precedent: ${e.toString()}'),
            backgroundColor: Colors.red.shade600,
            duration: const Duration(seconds: 3),
          ),
        );
      }
      return false;
    }
  }

  @override
  void dispose() {
    _progressSubscription?.cancel();
    _messageStreamSubscription?.cancel();
    _scrollController.dispose();
    _controller.dispose();
    if (widget.streamingService == null) {
      // Only dispose if we created the streaming service ourselves
      _streamingService.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.chatId == null) {
      return const Center(
        child: SelectableText(
          'Select a chat to start',
          style: TextStyle(
            fontSize: 16,
            color: Colors.grey,
          ),
        ),
      );
    }

    return FileDropHandler(
      enabled: !_sending,
      onFilesAdded: _handleFilesAdded,
      dropHintText: 'Drop files to send',
      child: Container(
        color: Colors.white,
        child: Column(
          children: [
          // Error Banner
          if (_error != null)
            Container(
              width: double.infinity,
              margin: const EdgeInsets.all(24),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.red.shade50,
                border: Border.all(color: Colors.red.shade200),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Icon(Icons.error_outline, color: Colors.red.shade400, size: 20),
                  const SizedBox(width: 12),
                  Expanded(
                    child: SelectableText(
                      _error!,
                      style: TextStyle(color: Colors.red.shade700, fontSize: 14),
                    ),
                  ),
                  IconButton(
                    onPressed: () => setState(() => _error = null),
                    icon: Icon(Icons.close, color: Colors.red.shade400, size: 20),
                    constraints: const BoxConstraints(),
                    padding: EdgeInsets.zero,
                  ),
                ],
              ),
            ),
          
          // Messages or Empty State Container
          _messages.isNotEmpty
              ? Expanded(
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 768), // max-w-3xl equivalent
                        child: ListView.separated(
                          controller: _scrollController,
                          reverse: false, // Normal chat behavior: scroll top to bottom
                          padding: const EdgeInsets.symmetric(vertical: 24),
                          itemCount: _messages.length + (_currentStreamingMessage != null ? 1 : 0),
                          separatorBuilder: (context, index) => const SizedBox(height: 24),
                          itemBuilder: (context, index) {
                            
                            if (_currentStreamingMessage != null && index == _messages.length) {
                              return Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  // Show reasoning above streaming content (not below)
                                  if (_currentWorkflow != null)
                                    Padding(
                                      padding: const EdgeInsets.only(bottom: 12),
                                      child: MessageReasoningDisplay(
                                        workflow: _currentWorkflow,
                                        progressBar: _showProgressBar ? _buildProgressBar() : null,
                                      ),
                                    ),
                                  
                                  ChatMessage(
                                    text: _currentStreamingMessage!.content,
                                    isUser: false,
                                    isStreaming: true,
                                  ),
                                ],
                              );
                            }
                            
                            // Regular message index (no adjustment needed since streaming is at the end)
                            final messageIndex = index;
                            final message = _messages[messageIndex];
                            final role = message['role']?.toString() ?? 'assistant';
                            final content = message['content']?.toString() ?? '';
                            final isUser = role == 'user';
                            
                            // Parse attachments from stored message data
                            List<FileAttachment>? messageAttachments;
                            if (message['attachments'] is List) {
                              final attachmentsList = message['attachments'] as List;
                              messageAttachments = attachmentsList
                                  .map((a) => FileAttachment.fromJson(a as Map<String, dynamic>))
                                  .toList();
                            }
                            
                            // Parse stored workflow data for assistant messages
                            WorkflowState? storedWorkflow;
                            if (!isUser && message['reasoning'] != null) {
                              storedWorkflow = _parseStoredReasoning(message['reasoning']);
                            }
                            
                            return Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // Show reasoning above AI content (not below)
                                if (storedWorkflow != null && !isUser)
                                  Padding(
                                    padding: const EdgeInsets.only(bottom: 12),
                                    child: MessageReasoningDisplay(workflow: storedWorkflow),
                                  ),
                                
                                // Show execution summary card for AI messages with execution path data
                                if (!isUser && message['has_state'] == true)
                                  FutureBuilder<Map<String, dynamic>?>(
                                    future: _fetchMessageState(message['id']),
                                    builder: (context, snapshot) {
                                      debugPrint('🎯 SUMMARY CARD: Message ID ${message['id']}, connection state: ${snapshot.connectionState}');

                                      if (snapshot.connectionState == ConnectionState.waiting) {
                                        return const SizedBox.shrink();
                                      }

                                      if (!snapshot.hasData) {
                                        debugPrint('❌ SUMMARY CARD: No data for message ${message['id']}');
                                        return const SizedBox.shrink();
                                      }

                                      final stateData = snapshot.data!;
                                      final allPaths = _extractAllPaths(stateData);
                                      final chosenPath = _extractChosenPath(stateData);

                                      debugPrint('🎯 SUMMARY CARD: Message ${message['id']} - allPaths: ${allPaths.length}, chosenPath: ${chosenPath?.length ?? 0}');

                                      // Only show summary card if we actually have path data (indicates find_path stage completed)
                                      final hasPathData = allPaths.isNotEmpty || (chosenPath?.isNotEmpty ?? false);
                                      if (!hasPathData) {
                                        debugPrint('❌ SUMMARY CARD: No path data found for message ${message['id']} - state did not go through find_path');
                                        return const SizedBox.shrink();
                                      }

                                      debugPrint('✅ SUMMARY CARD: Showing card for message ${message['id']} with ${allPaths.length} paths');
                                      
                                      // Parse message ID to int
                                      final messageId = message['id'] is int 
                                        ? message['id'] as int
                                        : int.parse(message['id'].toString());
                                      
                                      return SummaryCard(
                                        allPaths: allPaths,
                                        chosenPath: chosenPath,
                                        onTap: () => _selectExecutionPanel(messageId),
                                      );
                                    },
                                  ),
                                
                                
                                ChatMessage(
                                  text: content, 
                                  isUser: isUser,
                                  isStreaming: false,  // Saved messages are not streaming
                                  attachments: messageAttachments,
                                  chatId: widget.chatId,
                                  isPrecedentSaved: message['precedent_id'] != null,
                                  onSavePrecedent: () => _handleSavePrecedent(message),
                                ),
                              ],
                            );
                          },
                        ),
                      ),
                    ),
                  ),
                )
              : _loading
                  ? const Expanded(
                      child: Center(
                        child: CircularProgressIndicator(),
                      ),
                    )
                  : Expanded(
                      child: Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            SvgPicture.asset(
                              'assets/genesis.svg',
                              width: 100,
                              height: 100,
                              colorFilter: ColorFilter.mode(
                                Colors.black,
                                BlendMode.srcIn,
                              ),
                            ),
                            const SizedBox(height: 32),
                            // Chat input in center for empty state
                            ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: 768),
                              child: ChatInput(
                                key: _chatInputKey,
                                controller: _controller,
                                onSend: _sendMessage,
                                isLoading: _sending,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
          
          // Input Section (only show when messages exist)
          if (_messages.isNotEmpty)
            Container(
              padding: const EdgeInsets.all(24),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 768), // max-w-3xl equivalent
                  child: ChatInput(
                    key: _chatInputKey,
                    controller: _controller,
                    onSend: _sendMessage,
                    isLoading: _sending,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
  
  /// Build execution progress bar
  Widget _buildProgressBar() {
    final progressPct = _totalTools > 0 ? (_completedTools / _totalTools) : 0.0;
    final percentageText = '${(progressPct * 100).toInt()}%';
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Executing path',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: Colors.black,
                ),
              ),
              Text(
                percentageText,
                style: const TextStyle(
                  fontSize: 12,
                  color: Colors.black,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: progressPct,
              backgroundColor: const Color(0xFFF5F5F5), // Light gray (shaded white)
              valueColor: const AlwaysStoppedAnimation<Color>(Colors.black),
              minHeight: 8,
            ),
          ),
        ],
      ),
    );
  }
}
