import 'package:flutter/material.dart';
import 'package:gui/data/models/file_attachment.dart';
import 'package:gui/widgets/previews/image_preview.dart';
import 'package:gui/widgets/previews/audio_preview.dart';
import 'package:gui/widgets/previews/document_preview.dart';
import 'package:gui/widgets/previews/video_preview.dart';

/// Widget for previewing different types of files
/// Routes to the appropriate specialized preview widget
class FilePreview extends StatelessWidget {
  final FileAttachment attachment;
  final bool isCompact;
  final VoidCallback? onTap;
  final VoidCallback? onRemove;

  const FilePreview({
    super.key,
    required this.attachment,
    this.isCompact = false,
    this.onTap,
    this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    if (attachment.isImage) {
      return ImagePreview(
        attachment: attachment,
        isCompact: isCompact,
        onTap: onTap,
        onRemove: onRemove,
      );
    } else if (attachment.isAudio) {
      return AudioPreview(
        attachment: attachment,
        isCompact: isCompact,
        onTap: onTap,
        onRemove: onRemove,
      );
    } else if (attachment.isVideo) {
      return VideoPreview(
        attachment: attachment,
        isCompact: isCompact,
        onTap: onTap,
        onRemove: onRemove,
      );
    } else if (attachment.isDocument) {
      return DocumentPreview(
        attachment: attachment,
        isCompact: isCompact,
        onTap: onTap,
        onRemove: onRemove,
      );
    } else {
      // Default to document preview for unknown file types
      return DocumentPreview(
        attachment: attachment,
        isCompact: isCompact,
        onTap: onTap,
        onRemove: onRemove,
      );
    }
  }
}