import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../common/health_check.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:gui/data/services/chat_service.dart';

class Sidebar extends StatefulWidget {
  final bool isCollapsed;
  final VoidCallback onToggle;
  final double? width;
  final void Function(String chatId)? onSelect;

  const Sidebar({
    super.key,
    required this.isCollapsed,
    required this.onToggle,
    this.width,
    this.onSelect,
  });

  @override
  State<Sidebar> createState() => SidebarState();
}

class SidebarState extends State<Sidebar> {
  final ChatService _service = const ChatService();
  final List<Map<String, dynamic>> _chats = <Map<String, dynamic>>[];
  bool _loading = false;
  String? _error;
  String? _currentId;
  
  // Animation state for title updates
  final Map<String, String> _previousTitles = <String, String>{};
  final Map<String, String> _animatedTitles = <String, String>{};
  final Map<String, Timer> _animationTimers = <String, Timer>{};

  @override
  void initState() {
    super.initState();
    _loadChats();
  }

  Future<void> _loadChats() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await _service.listChats();
      setState(() {
        _chats
          ..clear()
          ..addAll(list);
        _loading = false;
      });
      
      // Initialize previous titles for tracking (first load only)
      if (_previousTitles.isEmpty) {
        for (final chat in _chats) {
          final id = chat['id']?.toString() ?? '';
          final title = chat['title']?.toString() ?? 'Untitled Conversation';
          _previousTitles[id] = title;
        }
      }
    } catch (e) {
      setState(() {
        _loading = false;
        _error = '$e';
      });
    }
  }

  // Public method to refresh chat list from external widgets
  Future<void> refreshChatList() async {
    debugPrint('🔄 SIDEBAR: Refreshing chat list...');
    await _loadChats();
    debugPrint('✅ SIDEBAR: Chat list refreshed');
  }

  // Public method to directly animate a title update for a specific chat
  Future<void> animateTitleUpdate(String chatId, String newTitle) async {
    debugPrint('🎬 SIDEBAR: Animating title update for $chatId: "$newTitle"');
    
    // Update the local chat data immediately so animation ends with correct title
    final chatIndex = _chats.indexWhere((c) => c['id']?.toString() == chatId);
    if (chatIndex != -1) {
      setState(() {
        _chats[chatIndex]['title'] = newTitle;
      });
      debugPrint('✅ SIDEBAR: Updated local chat data for $chatId to "$newTitle"');
    }
    
    _startTitleAnimation(chatId, newTitle);
    
    // Update the previous titles map to reflect the new title
    _previousTitles[chatId] = newTitle;
  }


  void _startTitleAnimation(String id, String toTitle) {
    debugPrint('🎬 SIDEBAR: Starting title animation for $id: "$toTitle"');
    
    // Clear any existing timer
    final existingTimer = _animationTimers[id];
    if (existingTimer != null) {
      existingTimer.cancel();
      _animationTimers.remove(id);
    }

    int reveal = 0;
    final String target = toTitle;
    final int length = target.length;

    // Hacker-style reveal animation parameters (slower for better visibility)
    const int intervalMs = 50;  // Slower updates to see character scrambling
    const int totalDurationMs = 1000;  // Longer duration to appreciate the effect
    final int ticksNeeded = max(1, (totalDurationMs / intervalMs).ceil());
    final int revealStep = max(1, (length / ticksNeeded).ceil());
    const String charset = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    final Random random = Random();

    final Timer timer = Timer.periodic(const Duration(milliseconds: intervalMs), (Timer timer) {
      final List<String> builder = List<String>.filled(length, '');
      
      for (int i = 0; i < length; i++) {
        if (i < reveal) {
          builder[i] = target[i];
        } else {
          builder[i] = charset[random.nextInt(charset.length)];
        }
      }
      
      final String display = builder.join();
      setState(() {
        _animatedTitles[id] = display;
      });

      reveal = min(length, reveal + revealStep);
      if (reveal >= length) {
        timer.cancel();
        _animationTimers.remove(id);
        setState(() {
          _animatedTitles.remove(id);
        });
        debugPrint('✨ SIDEBAR: Title animation completed for $id');
      }
    });
    
    _animationTimers[id] = timer;
  }

  @override
  void dispose() {
    // Clean up any active timers
    for (final timer in _animationTimers.values) {
      timer.cancel();
    }
    _animationTimers.clear();
    super.dispose();
  }

  Future<void> _handleNewChat() async {
    try {
      debugPrint('🆕 CREATING NEW CHAT...');
      final chat = await _service.createChat();
      final newChatId = chat['id']?.toString();
      
      debugPrint('✅ NEW CHAT CREATED: $newChatId');
      debugPrint('📋 CHAT DATA: $chat');
      
      setState(() {
        _chats.insert(0, chat);
        _currentId = newChatId;
      });
      
      // Notify parent about the new chat selection
      if (newChatId != null) {
        debugPrint('🎯 SELECTING NEW CHAT: $newChatId');
        widget.onSelect?.call(newChatId);
      }
      
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('New chat created')),
      );
    } catch (e) {
      debugPrint('❌ NEW CHAT CREATION FAILED: $e');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to create chat: $e')),
      );
    }
  }

  Future<void> _handleDeleteChat(String chatId) async {
    try {
      debugPrint('🗑️ DELETING CHAT: $chatId');
      debugPrint('🔍 CURRENTLY SELECTED CHAT: $_currentId');
      
      await _service.deleteChat(chatId);
      
      final wasCurrentlySelected = _currentId == chatId;
      
      setState(() {
        _chats.removeWhere((c) => c['id']?.toString() == chatId);
        if (_currentId == chatId) _currentId = null;
      });
      
      // If we deleted the currently selected chat, notify parent to clear selection
      if (wasCurrentlySelected) {
        debugPrint('🔄 DELETED CURRENTLY SELECTED CHAT - CLEARING SELECTION');
        widget.onSelect?.call(''); // Pass empty string to indicate no chat selected
      }
      
      debugPrint('✅ CHAT DELETED SUCCESSFULLY');
      
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Chat deleted')),
      );
    } catch (e) {
      debugPrint('❌ CHAT DELETION FAILED: $e');
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to delete chat: $e')),
      );
    }
  }

  void _handleSelect(String chatId) {
    setState(() {
      _currentId = chatId;
    });
    widget.onSelect?.call(chatId);
  }

  @override
  Widget build(BuildContext context) {
    final double currentWidth = widget.width ?? (widget.isCollapsed ? 48.0 : 256.0);
    final bool canShowExpandedContent = !widget.isCollapsed && currentWidth >= 200.0;

    return Column(
      children: [
        // Toggle Button
        Padding(
          padding: const EdgeInsets.all(12.0),
          child: Align(
            alignment: Alignment.centerLeft,
            child: InkWell(
              onTap: widget.onToggle,
              borderRadius: BorderRadius.circular(6),
              child: Container(
                width: 24,
                height: 24,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(6),
                ),
                child: SvgPicture.string(
                  '''<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M6.83496 3.99992C6.38353 4.00411 6.01421 4.0122 5.69824 4.03801C5.31232 4.06954 5.03904 4.12266 4.82227 4.20012L4.62207 4.28606C4.18264 4.50996 3.81498 4.85035 3.55859 5.26848L3.45605 5.45207C3.33013 5.69922 3.25006 6.01354 3.20801 6.52824C3.16533 7.05065 3.16504 7.71885 3.16504 8.66301V11.3271C3.16504 12.2712 3.16533 12.9394 3.20801 13.4618C3.25006 13.9766 3.33013 14.2909 3.45605 14.538L3.55859 14.7216C3.81498 15.1397 4.18266 15.4801 4.62207 15.704L4.82227 15.79C5.03904 15.8674 5.31234 15.9205 5.69824 15.9521C6.01398 15.9779 6.383 15.986 6.83398 15.9902L6.83496 3.99992ZM18.165 11.3271C18.165 12.2493 18.1653 12.9811 18.1172 13.5702C18.0745 14.0924 17.9916 14.5472 17.8125 14.9648L17.7295 15.1415C17.394 15.8 16.8834 16.3511 16.2568 16.7353L15.9814 16.8896C15.5157 17.1268 15.0069 17.2285 14.4102 17.2773C13.821 17.3254 13.0893 17.3251 12.167 17.3251H7.83301C6.91071 17.3251 6.17898 17.3254 5.58984 17.2773C5.06757 17.2346 4.61294 17.1508 4.19531 16.9716L4.01855 16.8896C3.36014 16.5541 2.80898 16.0434 2.4248 15.4169L2.27051 15.1415C2.03328 14.6758 1.93158 14.167 1.88281 13.5702C1.83468 12.9811 1.83496 12.2493 1.83496 11.3271V8.66301C1.83496 7.74072 1.83468 7.00898 1.88281 6.41985C1.93157 5.82309 2.03329 5.31432 2.27051 4.84856L2.4248 4.57317C2.80898 3.94666 3.36012 3.436 4.01855 3.10051L4.19531 3.0175C4.61285 2.83843 5.06771 2.75548 5.58984 2.71281C6.17898 2.66468 6.91071 2.66496 7.83301 2.66496H12.167C13.0893 2.66496 13.821 2.66468 14.4102 2.71281C15.0069 2.76157 15.5157 2.86329 15.9814 3.10051L16.2568 3.25481C16.8833 3.63898 17.394 4.19012 17.7295 4.84856L17.8125 5.02531C17.9916 5.44285 18.0745 5.89771 18.1172 6.41985C18.1653 7.00898 18.165 7.74072 18.165 8.66301V11.3271ZM8.16406 15.995H12.167C13.1112 15.995 13.7794 15.9947 14.3018 15.9521C14.8164 15.91 15.1308 15.8299 15.3779 15.704L15.5615 15.6015C15.9797 15.3451 16.32 14.9774 16.5439 14.538L16.6299 14.3378C16.7074 14.121 16.7605 13.8478 16.792 13.4618C16.8347 12.9394 16.835 12.2712 16.835 11.3271V8.66301C16.835 7.71885 16.8347 7.05065 16.792 6.52824C16.7605 6.14232 16.7073 5.86904 16.6299 5.65227L16.5439 5.45207C16.32 5.01264 15.9796 4.64498 15.5615 4.3886L15.3779 4.28606C15.1308 4.16013 14.8165 4.08006 14.3018 4.03801C13.7794 3.99533 13.1112 3.99504 12.167 3.99504H8.16406C8.16407 3.99667 8.16504 3.99829 8.16504 3.99992L8.16406 15.995Z" fill="currentColor"/>
                  </svg>''',
                  width: 20,
                  height: 20,
                  colorFilter: ColorFilter.mode(Colors.grey.shade700, BlendMode.srcIn),
                ),
              ),
            ),
          ),
        ),

        if (canShowExpandedContent) ...[
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 16),
              child: Column(
                children: [
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      child: Column(
                        children: [
                          Container(
                            margin: const EdgeInsets.only(bottom: 16),
                            child: InkWell(
                              onTap: _handleNewChat,
                              borderRadius: BorderRadius.circular(6),
                              child: Container(
                                width: double.infinity,
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 12,
                                  vertical: 8,
                                ),
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Row(
                                  children: [
                                    Container(
                                      width: 20,
                                      height: 20,
                                      alignment: Alignment.center,
                                      child: Icon(
                                        Icons.add,
                                        size: 16,
                                        color: Colors.grey.shade700,
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Text(
                                      'New Chat',
                                      style: TextStyle(
                                        fontSize: 14,
                                        fontWeight: FontWeight.w500,
                                        color: Colors.grey.shade700,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Padding(
                                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                  child: Text(
                                    'CHATS',
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w500,
                                      color: Colors.grey.shade500,
                                      letterSpacing: 0.5,
                                    ),
                                  ),
                                ),
                                if (_loading)
                                  const Padding(
                                    padding: EdgeInsets.all(12),
                                    child: SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(strokeWidth: 2),
                                    ),
                                  )
                                else if (_error != null)
                                  Padding(
                                    padding: const EdgeInsets.symmetric(horizontal: 12),
                                    child: SelectableText(
                                      _error!,
                                      style: TextStyle(color: Colors.red.shade700, fontSize: 12),
                                    ),
                                  )
                                else
                                  Expanded(
                                    child: _chats.isEmpty
                                        ? const Padding(
                                            padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                            child: SelectableText('No conversations yet', style: TextStyle(fontSize: 12)),
                                          )
                                        : ListView.builder(
                                            itemCount: _chats.length,
                                            itemBuilder: (context, index) {
                                              final c = _chats[index];
                                              final id = c['id']?.toString() ?? '';
                                              final title = (c['title']?.toString() ?? 'Untitled Conversation');
                                              final active = _currentId == id;
                                              return _buildConversationItem(
                                                id: id,
                                                title: title,
                                                isActive: active,
                                              );
                                            },
                                          ),
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.fromLTRB(12, 0, 12, 12),
                    child: HealthCheck(),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }

  Widget _buildConversationItem({required String id, required String title, required bool isActive}) {
    // Use animated title if available, otherwise use regular title
    final displayTitle = _animatedTitles[id] ?? title;
    
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 1),
      decoration: BoxDecoration(
        color: isActive ? Colors.grey.shade200 : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              // Left click to select chat
              onTap: () => _handleSelect(id),
              // Right click to copy title
              onSecondaryTap: () => _copyTitleToClipboard(displayTitle),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.all(8),
                child: Text(
                  displayTitle,
                  style: TextStyle(
                    fontSize: 14,
                    color: Colors.grey.shade800,
                  ),
                ),
              ),
            ),
          ),
          InkWell(
            onTap: () => _handleDeleteChat(id),
            borderRadius: BorderRadius.circular(4),
            child: Padding(
              padding: const EdgeInsets.all(4),
              child: Icon(
                Icons.delete_outline,
                size: 16,
                color: Colors.red.shade500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _copyTitleToClipboard(String title) async {
    try {
      await Clipboard.setData(ClipboardData(text: title));
      debugPrint('📋 SIDEBAR: Copied title to clipboard: "$title"');
      
      // Show a brief feedback
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Title copied: $title'),
            duration: const Duration(seconds: 2),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (e) {
      debugPrint('❌ SIDEBAR: Failed to copy title: $e');
    }
  }
}
