import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:gui/data/models/file_attachment.dart';
import 'package:gui/data/services/artifact_service.dart';
import 'package:gui/widgets/previews/file_preview.dart';

class ChatInput extends StatefulWidget {
  final TextEditingController controller;
  final Function(String message, List<FileAttachment> attachments) onSend;
  final bool isLoading;

  const ChatInput({
    super.key,
    required this.controller,
    required this.onSend,
    this.isLoading = false,
  });

  @override
  ChatInputState createState() => ChatInputState();
}

class ChatInputState extends State<ChatInput> {
  bool _hasText = false;
  final List<FileAttachment> _selectedAttachments = [];
  final ArtifactService _artifactService = ArtifactService();
  bool _isPickingFiles = false;

  /// Add dropped files to the attachment preview (called by parent widget)
  void addDroppedFiles(List<FileAttachment> attachments) {
    if (attachments.isNotEmpty) {
      setState(() {
        _selectedAttachments.addAll(attachments);
      });
      
      // Show success message
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('📎 Added ${attachments.length} file${attachments.length != 1 ? 's' : ''} to message'),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    }
  }

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_onTextChanged);
    _hasText = widget.controller.text.trim().isNotEmpty;
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onTextChanged);
    _artifactService.dispose();
    super.dispose();
  }

  void _onTextChanged() {
    final hasText = widget.controller.text.trim().isNotEmpty;
    if (hasText != _hasText) {
      setState(() {
        _hasText = hasText;
      });
    }
  }

  /// Pick files from device storage
  Future<void> _pickFiles() async {
    if (_isPickingFiles) return;

    setState(() {
      _isPickingFiles = true;
    });

    try {
      final files = await _artifactService.pickFiles(
        allowMultiple: true,
      );

      if (files.isNotEmpty) {
        // Validate files
        final validFiles = <File>[];
        for (final file in files) {
          if (_artifactService.validateFile(file)) {
            validFiles.add(file);
          } else {
            if (!mounted) return;
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('File "${file.path.split('/').last}" is too large or invalid'),
                backgroundColor: Colors.red,
              ),
            );
          }
        }

        if (validFiles.isNotEmpty) {
          final attachments = _artifactService.createAttachmentsFromFiles(validFiles);
          setState(() {
            _selectedAttachments.addAll(attachments);
          });
        }
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error picking files: $e'),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      setState(() {
        _isPickingFiles = false;
      });
    }
  }

  /// Remove a selected attachment
  void _removeAttachment(FileAttachment attachment) {
    setState(() {
      _selectedAttachments.remove(attachment);
    });
  }

  /// Send message with attachments
  void _sendMessage() {
    if (widget.isLoading) return;
    
    final message = widget.controller.text.trim();
    final hasContent = message.isNotEmpty || _selectedAttachments.isNotEmpty;
    
    if (hasContent) {
      widget.onSend(message, List.from(_selectedAttachments));
      widget.controller.clear();
      setState(() {
        _selectedAttachments.clear();
        _hasText = false;
      });
    }
  }

  bool get _canSend => !widget.isLoading && (_hasText || _selectedAttachments.isNotEmpty);

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.grey.shade50,
        borderRadius: BorderRadius.circular(24),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // File Attachments Preview
          if (_selectedAttachments.isNotEmpty) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.only(bottom: 12),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: _selectedAttachments.take(3).map((attachment) =>
                  FilePreview(
                    attachment: attachment,
                    isCompact: true,
                    onRemove: () => _removeAttachment(attachment),
                  )
                ).toList(),
              ),
            ),
          ],

          // Text Input Container
          Container(
            constraints: const BoxConstraints(maxHeight: 200),
            child: Focus(
              onKeyEvent: (node, event) {
                if (event is KeyDownEvent && event.logicalKey == LogicalKeyboardKey.enter) {
                  final isShiftPressed = HardwareKeyboard.instance.logicalKeysPressed
                      .contains(LogicalKeyboardKey.shiftLeft) ||
                      HardwareKeyboard.instance.logicalKeysPressed
                          .contains(LogicalKeyboardKey.shiftRight);
                  
                  if (isShiftPressed) {
                    // Shift+Enter: Allow new line (default behavior)
                    return KeyEventResult.ignored;
                  } else {
                    // Enter alone: Send message
                    if (_canSend) {
                      _sendMessage();
                    }
                    return KeyEventResult.handled;
                  }
                }
                return KeyEventResult.ignored;
              },
              child: TextField(
                controller: widget.controller,
                maxLines: null,
                keyboardType: TextInputType.multiline,
                textInputAction: TextInputAction.newline,
                onSubmitted: (value) {
                  if (_canSend) _sendMessage();
                },
                onTapOutside: (event) => FocusScope.of(context).unfocus(),
                  decoration: InputDecoration(
        hintText: _selectedAttachments.isEmpty 
            ? 'Ask anything, or drag & drop files' 
            : 'Add a message (optional)',
                    hintStyle: const TextStyle(color: Colors.grey),
                    border: InputBorder.none,
                    contentPadding: EdgeInsets.zero,
                  ),
                style: const TextStyle(
                  fontSize: 16,
                  height: 1.5,
                  color: Colors.black87,
                ),
              ),
            ),
          ),
          
          const SizedBox(height: 14),
          
          // Bottom Controls
          Row(
            children: [
              // File Upload Button
              Container(
                height: 32,
                width: 32,
                decoration: BoxDecoration(
                  color: _isPickingFiles 
                      ? Colors.blue.shade100 
                      : Colors.grey.shade50,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: IconButton(
                  onPressed: _isPickingFiles ? null : _pickFiles,
                  icon: _isPickingFiles
                      ? SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.blue.shade600,
                          ),
                        )
                      : Icon(
                          Icons.attach_file,
                          size: 16,
                          color: _isPickingFiles 
                              ? Colors.blue.shade600 
                              : Colors.grey.shade600,
                        ),
                  padding: EdgeInsets.zero,
                  tooltip: 'Attach files',
                ),
              ),
              
              // Attachment count indicator
              if (_selectedAttachments.isNotEmpty) ...[
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.blue.shade100,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    '${_selectedAttachments.length} file${_selectedAttachments.length != 1 ? 's' : ''}',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.blue.shade700,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
              
              const Spacer(),
              
              // Send Button
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                height: 32,
                width: 32,
                decoration: BoxDecoration(
                  color: _canSend ? Colors.black : Colors.grey.shade200,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: IconButton(
                  onPressed: _canSend ? _sendMessage : null,
                  icon: widget.isLoading
                      ? const SizedBox(
                          height: 16,
                          width: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : Icon(
                          Icons.arrow_upward,
                          size: 16,
                          color: _canSend ? Colors.white : Colors.grey.shade400,
                        ),
                  padding: EdgeInsets.zero,
                  tooltip: 'Send message',
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
