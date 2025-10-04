import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:gui/data/models/file_attachment.dart';
import 'package:gui/widgets/previews/file_preview.dart';

class ChatMessage extends StatefulWidget {
  final String text;
  final bool isUser;
  final bool isStreaming;
  final List<FileAttachment>? attachments;
  final String? chatId;
  final bool isPrecedentSaved;
  final Future<bool> Function()? onSavePrecedent;
  
  const ChatMessage({
    super.key,
    required this.text,
    required this.isUser,
    this.isStreaming = false,
    this.attachments,
    this.chatId,
    this.isPrecedentSaved = false,
    this.onSavePrecedent,
  });

  @override
  State<ChatMessage> createState() => _ChatMessageState();
}

class _ChatMessageState extends State<ChatMessage> {
  bool _copied = false;
  bool _isSavingPrecedent = false;

  /// Get formatted text with <file> tags replaced by just filenames
  String _getFormattedText() {
    if (widget.isUser) {
      return widget.text;
    }
    
    // For assistant messages, replace <file>full/path/filename.ext</file> with just filename.ext
    return widget.text.replaceAllMapped(
      RegExp(r'<file>(.*?)<\/file>', caseSensitive: false),
      (match) {
        final fullPath = match.group(1)?.trim() ?? '';
        if (fullPath.isNotEmpty) {
          // Extract just the filename from the path
          final filename = fullPath.split('/').last;
          return filename;
        }
        return '';
      },
    ).trim();
  }

  @override
  Widget build(BuildContext context) {
    // For assistant messages, replace <file> paths with just filename
    List<FileAttachment> allAttachments = [];
    String displayText = _getFormattedText();
    
    // Add any direct attachments (these will be shown as previews)
    if (widget.attachments != null && widget.attachments!.isNotEmpty) {
      allAttachments.addAll(widget.attachments!);
    }
    
    final hasAttachments = allAttachments.isNotEmpty;
    final hasText = displayText.trim().isNotEmpty;
    
    return Row(
      mainAxisAlignment: widget.isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Flexible(
          child: Container(
            constraints: const BoxConstraints(maxWidth: 650),
            child: Column(
              crossAxisAlignment: widget.isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                // File attachments
                if (hasAttachments) ...[
                  Container(
                    margin: EdgeInsets.only(
                      bottom: hasText ? 8 : 0,
                    ),
                    child: Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: allAttachments.map((attachment) => 
                        FilePreview(
                          attachment: attachment,
                          isCompact: false,
                          onTap: () => _openFile(context, attachment),
                        )
                      ).toList(),
                    ),
                  ),
                ],
                
                // Text content with underlined filenames
                if (hasText)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    decoration: BoxDecoration(
                      color: widget.isUser ? Colors.grey.shade100 : Colors.transparent,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: SelectableText.rich(
                      TextSpan(
                        children: [
                          ..._buildTextSpansWithUnderlinedFiles(displayText, widget.text, widget.isUser),
                          if (widget.isStreaming && !widget.isUser)
                            const TextSpan(
                              text: '▌',
                              style: TextStyle(
                                fontSize: 16,
                                color: Colors.black54,
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                
                // Action buttons for assistant messages (only show if has meaningful content)
                if (!widget.isUser && !widget.isStreaming && widget.text.trim().isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _buildCopyButton(),
                        const SizedBox(width: 10),
                        _buildThumbsUpButton(),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
      ],
    );
  }
  
  Widget _buildCopyButton() {
    return InkWell(
      onTap: _handleCopy,
      borderRadius: BorderRadius.circular(4),
      child: Container(
        width: 28,
        height: 28,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(4),
          color: Colors.transparent,
        ),
        child: Center(
          child: _copied
              ? const Icon(Icons.check, size: 16, color: Colors.black87)
              : Icon(Icons.content_copy, size: 16, color: Colors.grey.shade600),
        ),
      ),
    );
  }
  
  Widget _buildThumbsUpButton() {
    // Disable interaction during loading
    if (_isSavingPrecedent) {
      return Container(
        width: 28,
        height: 28,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(4),
          color: Colors.transparent,
        ),
        child: const Center(
          child: SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(Colors.grey),
            ),
          ),
        ),
      );
    }
    
    // Both saved and unsaved states are clickable
    return InkWell(
      onTap: _handleSavePrecedent,
      borderRadius: BorderRadius.circular(4),
      highlightColor: Colors.grey.shade600,
      splashColor: Colors.grey.shade600,
      child: Container(
        width: 28,
        height: 28,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(4),
          color: Colors.transparent,
        ),
        child: Center(
          child: Icon(
            widget.isPrecedentSaved ? Icons.thumb_up : Icons.thumb_up_outlined,
            size: 16,
            color: Colors.grey.shade600,
          ),
        ),
      ),
    );
  }
  
  Future<void> _handleSavePrecedent() async {
    if (widget.onSavePrecedent == null) return;
    
    setState(() => _isSavingPrecedent = true);
    
    try {
      final success = await widget.onSavePrecedent!();
      if (mounted && success) {
        // The parent will update isPrecedentSaved, triggering a rebuild
        setState(() => _isSavingPrecedent = false);
      } else if (mounted) {
        setState(() => _isSavingPrecedent = false);
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isSavingPrecedent = false);
        // Show error snackbar
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to toggle precedent: ${e.toString()}'),
            backgroundColor: Colors.red.shade600,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    }
  }
  
  Future<void> _handleCopy() async {
    try {
      // Copy the formatted text (with <file> tags replaced by filenames)
      await Clipboard.setData(ClipboardData(text: _getFormattedText()));
      setState(() => _copied = true);
      Future.delayed(const Duration(milliseconds: 1500), () {
        if (mounted) {
          setState(() => _copied = false);
        }
      });
    } catch (e) {
      // Silently fail
    }
  }
  
  /// Build TextSpans with underlined filenames for <file> tags
  List<TextSpan> _buildTextSpansWithUnderlinedFiles(String displayText, String originalText, bool isUser) {
    if (isUser) {
      // User messages don't have file tags
      return [
        TextSpan(
          text: displayText,
          style: const TextStyle(
            fontSize: 16,
            height: 1.5,
            color: Colors.black87,
          ),
        ),
      ];
    }
    
    final List<TextSpan> spans = [];
    final fileRegex = RegExp(r'<file>(.*?)<\/file>', caseSensitive: false);
    final matches = fileRegex.allMatches(originalText).toList();
    
    if (matches.isEmpty) {
      // No file tags, return simple span
      return [
        TextSpan(
          text: displayText,
          style: const TextStyle(
            fontSize: 16,
            height: 1.5,
            color: Colors.black87,
          ),
        ),
      ];
    }
    
    int currentIndex = 0;
    
    for (final match in matches) {
      // Add text before the file tag
      if (match.start > currentIndex) {
        final beforeText = originalText.substring(currentIndex, match.start);
        spans.add(TextSpan(
          text: beforeText,
          style: const TextStyle(
            fontSize: 16,
            height: 1.5,
            color: Colors.black87,
          ),
        ));
      }
      
      // Add underlined filename
      final fullPath = match.group(1)?.trim() ?? '';
      if (fullPath.isNotEmpty) {
        final filename = fullPath.split('/').last;
        spans.add(TextSpan(
          text: filename,
          style: const TextStyle(
            fontSize: 16,
            height: 1.5,
            color: Colors.black87,
            decoration: TextDecoration.underline,
          ),
        ));
      }
      
      currentIndex = match.end;
    }
    
    // Add remaining text after last file tag
    if (currentIndex < originalText.length) {
      final afterText = originalText.substring(currentIndex);
      spans.add(TextSpan(
        text: afterText,
        style: const TextStyle(
          fontSize: 16,
          height: 1.5,
          color: Colors.black87,
        ),
      ));
    }
    
    return spans;
  }
  
  /// Open file attachment (placeholder for future implementation)
  void _openFile(BuildContext context, FileAttachment attachment) {
    // TODO: Implement file opening logic (preview dialog, download, etc.)
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Opening ${attachment.filename}...'),
        duration: const Duration(seconds: 1),
      ),
    );
  }
}
