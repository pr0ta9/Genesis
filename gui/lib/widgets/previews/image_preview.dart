import 'dart:io';
import 'package:flutter/material.dart';
import 'package:gui/data/models/file_attachment.dart';
import 'package:gui/core/config.dart';

/// Widget for previewing image files
class ImagePreview extends StatefulWidget {
  final FileAttachment attachment;
  final bool isCompact;
  final VoidCallback? onTap;
  final VoidCallback? onRemove;

  const ImagePreview({
    super.key,
    required this.attachment,
    this.isCompact = false,
    this.onTap,
    this.onRemove,
  });

  @override
  State<ImagePreview> createState() => _ImagePreviewState();
}

/// Modal dialog that shows the full-size image with semi-transparent background
class ImageModal extends StatelessWidget {
  final ImageProvider imageProvider;
  final String filename;

  const ImageModal({
    super.key,
    required this.imageProvider,
    required this.filename,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black.withValues(alpha: 0.5), // 50% opacity grey/black background
      child: Stack(
        children: [
          // Tap anywhere to close
          GestureDetector(
            onTap: () => Navigator.of(context).pop(),
            child: Container(
              color: Colors.transparent,
              width: double.infinity,
              height: double.infinity,
            ),
          ),
          // Centered image
          Center(
            child: GestureDetector(
              onTap: () {}, // Prevent closing when tapping the image itself
              child: Container(
                constraints: BoxConstraints(
                  maxWidth: MediaQuery.of(context).size.width * 0.9,
                  maxHeight: MediaQuery.of(context).size.height * 0.9,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Close button
                    Align(
                      alignment: Alignment.topRight,
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: IconButton(
                          icon: const Icon(Icons.close, color: Colors.white, size: 32),
                          onPressed: () => Navigator.of(context).pop(),
                          tooltip: 'Close',
                        ),
                      ),
                    ),
                    // Image with white background
                    Flexible(
                      child: Container(
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(8),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.3),
                              blurRadius: 20,
                              spreadRadius: 5,
                            ),
                          ],
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: Image(
                            image: imageProvider,
                            fit: BoxFit.contain,
                            errorBuilder: (context, error, stackTrace) {
                              return Container(
                                padding: const EdgeInsets.all(40),
                                child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    const Icon(
                                      Icons.broken_image,
                                      size: 64,
                                      color: Colors.grey,
                                    ),
                                    const SizedBox(height: 16),
                                    Text(
                                      'Failed to load image',
                                      style: TextStyle(
                                        color: Colors.grey.shade700,
                                        fontSize: 16,
                                      ),
                                    ),
                                  ],
                                ),
                              );
                            },
                          ),
                        ),
                      ),
                    ),
                    // Filename at the bottom
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        filename,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ImagePreviewState extends State<ImagePreview> {
  bool _hasError = false;

  void _handleTap() {
    if (widget.onTap != null) {
      // If a custom onTap is provided, use it
      widget.onTap!();
    } else if (!_hasError) {
      // Otherwise, show the image modal
      showDialog(
        context: context,
        barrierColor: Colors.transparent, // We handle the background in ImageModal
        builder: (context) => ImageModal(
          imageProvider: _getImageProvider(),
          filename: widget.attachment.filename,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: _handleTap,
      child: Container(
        constraints: BoxConstraints(
          maxHeight: widget.isCompact ? 100 : 200,
          maxWidth: widget.isCompact ? 150 : 300,
        ),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.grey.shade300),
        ),
        child: Stack(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: _hasError
                  ? _buildErrorPlaceholder()
                  : Image(
                      image: _getImageProvider(),
                      fit: BoxFit.cover,
                      width: double.infinity,
                      height: double.infinity,
                      errorBuilder: (context, error, stackTrace) {
                        WidgetsBinding.instance.addPostFrameCallback((_) {
                          if (mounted) {
                            setState(() {
                              _hasError = true;
                            });
                          }
                        });
                        return _buildErrorPlaceholder();
                      },
                    ),
            ),
            if (widget.onRemove != null)
              Positioned(
                top: 8,
                right: 8,
                child: GestureDetector(
                  onTap: widget.onRemove,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: const BoxDecoration(
                      color: Colors.black,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.close,
                      color: Colors.white,
                      size: 16,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorPlaceholder() {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: Colors.grey.shade100,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.broken_image,
            size: widget.isCompact ? 24 : 48,
            color: Colors.grey.shade400,
          ),
          const SizedBox(height: 8),
          Text(
            'Failed to load image',
            style: TextStyle(
              color: Colors.grey.shade600,
              fontSize: widget.isCompact ? 10 : 12,
            ),
          ),
          Text(
            widget.attachment.filename,
            style: TextStyle(
              color: Colors.grey.shade500,
              fontSize: widget.isCompact ? 8 : 10,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  ImageProvider _getImageProvider() {
    if (widget.attachment.path != null && !widget.attachment.path!.startsWith('http')) {
      // Check if it's a local file path (Windows or Unix style)
      if ((widget.attachment.path!.startsWith('/') || widget.attachment.path!.contains(':')) && 
          File(widget.attachment.path!).existsSync()) {
        // Local file that exists on this device
        return FileImage(File(widget.attachment.path!));
      }
      
      // Otherwise try to construct backend URL
      final url = widget.attachment.getDisplayUrl(AppConfig.apiBaseUrl);
      if (url.isNotEmpty) {
        return NetworkImage(url);
      }
    } else if (widget.attachment.url != null && widget.attachment.url!.startsWith('http')) {
      // Direct HTTP URL
      return NetworkImage(widget.attachment.url!);
    }
    
    // Fallback - try backend URL construction
    final url = widget.attachment.getDisplayUrl(AppConfig.apiBaseUrl);
    return NetworkImage(url);
  }
}
