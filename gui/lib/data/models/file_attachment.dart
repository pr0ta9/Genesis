/// Represents a file attachment that can be uploaded or displayed in chat
class FileAttachment {
  final String filename;
  final String? path;
  final String? url;
  final int? size;
  final String mimeType;
  final DateTime? uploadedAt;

  const FileAttachment({
    required this.filename,
    this.path,
    this.url,
    this.size,
    required this.mimeType,
    this.uploadedAt,
  });

  /// Factory constructor for creating from API response
  factory FileAttachment.fromJson(Map<String, dynamic> json) {
    return FileAttachment(
      filename: json['filename'] as String,
      path: json['path'] as String?,
      url: json['url'] as String?,
      size: json['size'] as int?,
      mimeType: json['mime_type'] as String? ?? 'application/octet-stream',
      uploadedAt: json['uploaded_at'] != null 
          ? DateTime.parse(json['uploaded_at'] as String)
          : null,
    );
  }

  /// Convert to JSON for API requests
  Map<String, dynamic> toJson() {
    return {
      'filename': filename,
      if (path != null) 'path': path,
      if (url != null) 'url': url,
      if (size != null) 'size': size,
      'mime_type': mimeType,
      if (uploadedAt != null) 'uploaded_at': uploadedAt!.toIso8601String(),
    };
  }

  /// Check if this attachment is an image
  bool get isImage {
    final ext = filename.toLowerCase();
    return ext.endsWith('.png') ||
        ext.endsWith('.jpg') ||
        ext.endsWith('.jpeg') ||
        ext.endsWith('.gif') ||
        ext.endsWith('.webp') ||
        mimeType.startsWith('image/');
  }

  /// Check if this attachment is an audio file
  bool get isAudio {
    final ext = filename.toLowerCase();
    return ext.endsWith('.mp3') ||
        ext.endsWith('.wav') ||
        ext.endsWith('.m4a') ||
        ext.endsWith('.ogg') ||
        ext.endsWith('.webm') ||
        ext.endsWith('.flac') ||
        mimeType.startsWith('audio/');
  }

  /// Check if this attachment is a video file
  bool get isVideo {
    final ext = filename.toLowerCase();
    return ext.endsWith('.mp4') ||
        ext.endsWith('.mov') ||
        ext.endsWith('.avi') ||
        ext.endsWith('.webm') ||
        mimeType.startsWith('video/');
  }

  /// Check if this attachment is a text/document file
  bool get isDocument {
    final ext = filename.toLowerCase();
    return ext.endsWith('.txt') ||
        ext.endsWith('.pdf') ||
        ext.endsWith('.doc') ||
        ext.endsWith('.docx') ||
        mimeType.startsWith('text/') ||
        mimeType == 'application/pdf';
  }

  /// Get the display URL for this attachment
  String getDisplayUrl(String baseApiUrl) {
    if (url != null && url!.startsWith('http')) {
      return url!;
    }
    
    if (path != null) {
      // Handle Docker container paths for inputs and outputs
      // baseApiUrl already includes /api/v1 prefix
      if (path!.contains('/outputs/')) {
        // Outputs use query parameter pattern: /artifacts/outputs/file?path=chat_id/msg_id/file.png
        final relativePath = path!.split('/outputs/').last;
        return '$baseApiUrl/artifacts/outputs/file?path=${Uri.encodeComponent(relativePath)}';
      } else if (path!.contains('/inputs/')) {
        // Inputs use path parameter pattern: /artifacts/chat_id/file/filename.png
        final parts = path!.split('/');
        if (parts.length >= 2) {
          final chatId = parts[parts.length - 2];
          final filename = parts.last;
          return '$baseApiUrl/artifacts/${Uri.encodeComponent(chatId)}/file/${Uri.encodeComponent(filename)}';
        }
      }
    }
    
    return url ?? '';
  }

  /// Create a copy with updated properties
  FileAttachment copyWith({
    String? filename,
    String? path,
    String? url,
    int? size,
    String? mimeType,
    DateTime? uploadedAt,
  }) {
    return FileAttachment(
      filename: filename ?? this.filename,
      path: path ?? this.path,
      url: url ?? this.url,
      size: size ?? this.size,
      mimeType: mimeType ?? this.mimeType,
      uploadedAt: uploadedAt ?? this.uploadedAt,
    );
  }

  @override
  String toString() {
    return 'FileAttachment(filename: $filename, mimeType: $mimeType, size: $size)';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is FileAttachment &&
        other.filename == filename &&
        other.path == path &&
        other.url == url &&
        other.size == size &&
        other.mimeType == mimeType &&
        other.uploadedAt == uploadedAt;
  }

  @override
  int get hashCode {
    return Object.hash(filename, path, url, size, mimeType, uploadedAt);
  }
}

/// Response from the artifact upload API
class ArtifactUploadResponse {
  final List<FileAttachment> files;
  final int count;

  const ArtifactUploadResponse({
    required this.files,
    required this.count,
  });

  factory ArtifactUploadResponse.fromJson(Map<String, dynamic> json) {
    final filesList = (json['files'] as List<dynamic>?) ?? [];
    return ArtifactUploadResponse(
      files: filesList.map((f) => FileAttachment.fromJson(f as Map<String, dynamic>)).toList(),
      count: json['count'] as int? ?? 0,
    );
  }
}

/// Response from the artifact list API
class ArtifactListResponse {
  final List<FileAttachment> files;
  final int count;

  const ArtifactListResponse({
    required this.files,
    required this.count,
  });

  factory ArtifactListResponse.fromJson(Map<String, dynamic> json) {
    final filesList = (json['files'] as List<dynamic>?) ?? [];
    return ArtifactListResponse(
      files: filesList.map((f) => FileAttachment.fromJson(f as Map<String, dynamic>)).toList(),
      count: json['count'] as int? ?? 0,
    );
  }
}
