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

class _ImagePreviewState extends State<ImagePreview> {
  bool _hasError = false;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onTap,
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
