import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:desktop_drop/desktop_drop.dart';
import 'package:cross_file/cross_file.dart';
import 'package:pasteboard/pasteboard.dart';
import 'package:path_provider/path_provider.dart';
import 'package:gui/data/models/file_attachment.dart';
import 'package:gui/data/services/artifact_service.dart';

/// Simple and reliable drag & drop handler widget using desktop_drop
class FileDropHandler extends StatefulWidget {
  final Widget child;
  final Function(List<FileAttachment> attachments) onFilesAdded;
  final bool enabled;
  final String? dropHintText;

  const FileDropHandler({
    super.key,
    required this.child,
    required this.onFilesAdded,
    this.enabled = true,
    this.dropHintText,
  });

  @override
  State<FileDropHandler> createState() => _FileDropHandlerState();
}

class _FileDropHandlerState extends State<FileDropHandler> {
  bool _isDragging = false;
  bool _isProcessing = false;
  final ArtifactService _artifactService = ArtifactService();

  @override
  void dispose() {
    _artifactService.dispose();
    super.dispose();
  }

  /// Handle dropped files from drag & drop
  Future<void> _handleDroppedFiles(List<XFile> files) async {
    if (!widget.enabled || _isProcessing) return;
    
    setState(() {
      _isProcessing = true;
      _isDragging = false;
    });

    try {
      debugPrint('📁 Processing ${files.length} dropped files...');
      
      final validFiles = <File>[];
      
      for (final xFile in files) {
        final file = File(xFile.path);
        if (await file.exists()) {
          if (_artifactService.validateFile(file)) {
            validFiles.add(file);
            debugPrint('✅ Valid file: ${xFile.name} (${file.lengthSync()} bytes)');
          } else {
            debugPrint('❌ File too large or invalid: ${xFile.name}');
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('File "${xFile.name}" is too large (max 25MB) or invalid format'),
                  backgroundColor: Colors.orange,
                ),
              );
            }
          }
        } else {
          debugPrint('❌ File does not exist: ${xFile.path}');
        }
      }
      
      if (validFiles.isNotEmpty) {
        final attachments = _artifactService.createAttachmentsFromFiles(validFiles);
        widget.onFilesAdded(attachments);
        
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('✅ Dropped ${validFiles.length} file${validFiles.length != 1 ? 's' : ''} successfully'),
              backgroundColor: Colors.green,
              duration: const Duration(seconds: 2),
            ),
          );
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('❌ No valid files could be processed'),
              backgroundColor: Colors.red,
              duration: Duration(seconds: 3),
            ),
          );
        }
      }
    } catch (e) {
      debugPrint('❌ Drop error: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('❌ Failed to process files: ${e.toString()}'),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isProcessing = false;
        });
      }
    }
  }

  /// Handle clipboard paste for images and files
  Future<void> _handleClipboardPaste() async {
    if (!widget.enabled || _isProcessing) return;
    
    try {
      // Check if clipboard has image
      final imageBytes = await Pasteboard.image;
      if (imageBytes != null && imageBytes.isNotEmpty) {
        await _handlePastedImage(imageBytes);
        return;
      }

      // Check if clipboard has files
      final files = await Pasteboard.files();
      if (files.isNotEmpty) {
        await _handlePastedFiles(files);
        return;
      }

      // If no files or images, let Flutter handle normal text paste
      // (do nothing and let the default behavior work)
      
    } catch (e) {
      debugPrint('❌ Clipboard error: $e');
      // If pasteboard fails, let normal paste work
    }
  }

  /// Handle pasted image from clipboard
  Future<void> _handlePastedImage(Uint8List imageBytes) async {
    setState(() {
      _isProcessing = true;
    });

    try {
      // Save image to temporary file
      final tempDir = await getTemporaryDirectory();
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final tempFile = File('${tempDir.path}/pasted_image_$timestamp.png');
      await tempFile.writeAsBytes(imageBytes);

      debugPrint('📋 Saved pasted image: ${tempFile.path} (${imageBytes.length} bytes)');

      final attachment = _artifactService.createAttachmentsFromFiles([tempFile]);
      widget.onFilesAdded(attachment);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('📋 Pasted image from clipboard successfully'),
            backgroundColor: Colors.green,
            duration: Duration(seconds: 2),
          ),
        );
      }
    } catch (e) {
      debugPrint('❌ Failed to handle pasted image: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('❌ Failed to paste image: ${e.toString()}'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isProcessing = false;
        });
      }
    }
  }

  /// Handle pasted files from clipboard
  Future<void> _handlePastedFiles(List<String> filePaths) async {
    setState(() {
      _isProcessing = true;
    });

    try {
      final validFiles = <File>[];
      
      for (final path in filePaths) {
        final file = File(path);
        if (await file.exists()) {
          if (_artifactService.validateFile(file)) {
            validFiles.add(file);
          }
        }
      }

      if (validFiles.isNotEmpty) {
        final attachments = _artifactService.createAttachmentsFromFiles(validFiles);
        widget.onFilesAdded(attachments);

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('📋 Pasted ${validFiles.length} file${validFiles.length != 1 ? 's' : ''} from clipboard'),
              backgroundColor: Colors.green,
              duration: const Duration(seconds: 2),
            ),
          );
        }
      }
    } catch (e) {
      debugPrint('❌ Failed to handle pasted files: $e');
    } finally {
      if (mounted) {
        setState(() {
          _isProcessing = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Focus(
      autofocus: false,
      onKeyEvent: (node, event) {
        // Handle Ctrl+V / Cmd+V to check for files/images
        if (event is KeyDownEvent && widget.enabled) {
          final isCtrlPressed = HardwareKeyboard.instance.logicalKeysPressed
              .contains(LogicalKeyboardKey.controlLeft) ||
              HardwareKeyboard.instance.logicalKeysPressed
              .contains(LogicalKeyboardKey.controlRight);
          
          final isCmdPressed = HardwareKeyboard.instance.logicalKeysPressed
              .contains(LogicalKeyboardKey.metaLeft) ||
              HardwareKeyboard.instance.logicalKeysPressed
              .contains(LogicalKeyboardKey.metaRight);
          
          final isPasteKey = event.logicalKey == LogicalKeyboardKey.keyV;
          
          if ((isCtrlPressed || isCmdPressed) && isPasteKey) {
            // Handle clipboard paste (images/files only)
            _handleClipboardPaste();
            // Always return ignored to allow normal text paste to work
            return KeyEventResult.ignored;
          }
        }
        return KeyEventResult.ignored;
      },
      child: DropTarget(
        onDragEntered: (detail) {
          if (widget.enabled && !_isProcessing) {
            debugPrint('🎯 Files dragged into area');
            setState(() {
              _isDragging = true;
            });
          }
        },
        onDragExited: (detail) {
          debugPrint('🎯 Files dragged out of area');
          setState(() {
            _isDragging = false;
          });
        },
        onDragDone: (detail) {
          debugPrint('🎯 Files dropped: ${detail.files.length} files');
          if (detail.files.isNotEmpty) {
            _handleDroppedFiles(detail.files);
          } else {
            debugPrint('❌ No files in drop event');
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('❌ No files detected in drop'),
                  backgroundColor: Colors.orange,
                ),
              );
            }
          }
        },
        child: Stack(
          children: [
            // Main content
            widget.child,
            
            // Clean white drag overlay - shown when files are being dragged over
            if (_isDragging && widget.enabled)
              Container(
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.5), // 50% transparent white background
                ),
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // File icons (simple folder/document icons)
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 48,
                            height: 48,
                            decoration: BoxDecoration(
                              color: Colors.blue.shade400,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Icon(
                              Icons.folder,
                              color: Colors.white,
                              size: 28,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Container(
                            width: 48,
                            height: 48,
                            decoration: BoxDecoration(
                              color: Colors.blue.shade600,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Icon(
                              Icons.description,
                              color: Colors.white,
                              size: 28,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Container(
                            width: 48,
                            height: 48,
                            decoration: BoxDecoration(
                              color: Colors.blue.shade500,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: const Icon(
                              Icons.insert_chart,
                              color: Colors.white,
                              size: 28,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 24),
                      // Main title
                      const Text(
                        'Add anything',
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.w600,
                          color: Colors.black87,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),
                      // Subtitle
                      Text(
                        'Drop any file here to add it to the conversation',
                        style: TextStyle(
                          fontSize: 16,
                          color: Colors.grey.shade600,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
              
              // Processing overlay - shown when files are being processed
              if (_isProcessing)
                Container(
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        CircularProgressIndicator(
                          color: Colors.white,
                          strokeWidth: 3,
                        ),
                        SizedBox(height: 16),
                        Text(
                          'Processing files...',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
          ],
        ),
      ),
    );
  }
}
