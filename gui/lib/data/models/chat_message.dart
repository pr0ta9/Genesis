import 'package:gui/data/models/file_attachment.dart';

/// Represents a chat message with optional file attachments
class ChatMessage {
  final String id;
  final String content;
  final String role; // 'user' or 'assistant'
  final DateTime timestamp;
  final List<FileAttachment> attachments;
  final Map<String, dynamic>? metadata;
  final bool isStreaming;

  const ChatMessage({
    required this.id,
    required this.content,
    required this.role,
    required this.timestamp,
    this.attachments = const [],
    this.metadata,
    this.isStreaming = false,
  });

  /// Create a user message with attachments
  factory ChatMessage.user({
    required String content,
    List<FileAttachment> attachments = const [],
    Map<String, dynamic>? metadata,
  }) {
    return ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      content: content,
      role: 'user',
      timestamp: DateTime.now(),
      attachments: attachments,
      metadata: metadata,
    );
  }

  /// Create an assistant message (usually from streaming)
  factory ChatMessage.assistant({
    String? id,
    required String content,
    List<FileAttachment> attachments = const [],
    Map<String, dynamic>? metadata,
    bool isStreaming = false,
  }) {
    return ChatMessage(
      id: id ?? DateTime.now().millisecondsSinceEpoch.toString(),
      content: content,
      role: 'assistant',
      timestamp: DateTime.now(),
      attachments: attachments,
      metadata: metadata,
      isStreaming: isStreaming,
    );
  }

  /// Factory constructor for creating from API response
  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    final attachmentsList = (json['attachments'] as List<dynamic>?) ?? [];
    
    return ChatMessage(
      id: json['id']?.toString() ?? DateTime.now().millisecondsSinceEpoch.toString(),
      content: json['content'] as String? ?? '',
      role: json['role'] as String? ?? 'assistant',
      timestamp: json['timestamp'] != null 
          ? DateTime.parse(json['timestamp'] as String)
          : DateTime.now(),
      attachments: attachmentsList
          .map((a) => FileAttachment.fromJson(a as Map<String, dynamic>))
          .toList(),
      metadata: json['metadata'] as Map<String, dynamic>?,
      isStreaming: json['is_streaming'] as bool? ?? false,
    );
  }

  /// Convert to JSON for API requests
  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'content': content,
      'role': role,
      'timestamp': timestamp.toIso8601String(),
      'attachments': attachments.map((a) => a.toJson()).toList(),
      if (metadata != null) 'metadata': metadata,
      'is_streaming': isStreaming,
    };
  }

  /// Check if this message has any attachments
  bool get hasAttachments => attachments.isNotEmpty;

  /// Check if this message has any image attachments
  bool get hasImages => attachments.any((a) => a.isImage);

  /// Check if this message has any audio attachments
  bool get hasAudio => attachments.any((a) => a.isAudio);

  /// Check if this message has any document attachments
  bool get hasDocuments => attachments.any((a) => a.isDocument);

  /// Get all image attachments
  List<FileAttachment> get imageAttachments => 
      attachments.where((a) => a.isImage).toList();

  /// Get all audio attachments
  List<FileAttachment> get audioAttachments => 
      attachments.where((a) => a.isAudio).toList();

  /// Get all document attachments
  List<FileAttachment> get documentAttachments => 
      attachments.where((a) => a.isDocument).toList();

  /// Extract file references from assistant message content (from <file> tags)
  List<String> getFileReferences() {
    if (role != 'assistant') return [];
    
    final regex = RegExp(r'<file>([\s\S]*?)<\/file>', caseSensitive: false);
    final matches = regex.allMatches(content);
    
    return matches
        .map((match) => match.group(1)?.trim())
        .where((path) => path != null && path.isNotEmpty)
        .cast<String>()
        .toList();
  }

  /// Get content without <file> tags (clean content for display)
  String get cleanContent {
    if (role != 'assistant') return content;
    
    return content.replaceAll(
      RegExp(r'<file>[\s\S]*?<\/file>', caseSensitive: false),
      '',
    ).trim();
  }

  /// Create a copy with updated properties
  ChatMessage copyWith({
    String? id,
    String? content,
    String? role,
    DateTime? timestamp,
    List<FileAttachment>? attachments,
    Map<String, dynamic>? metadata,
    bool? isStreaming,
  }) {
    return ChatMessage(
      id: id ?? this.id,
      content: content ?? this.content,
      role: role ?? this.role,
      timestamp: timestamp ?? this.timestamp,
      attachments: attachments ?? this.attachments,
      metadata: metadata ?? this.metadata,
      isStreaming: isStreaming ?? this.isStreaming,
    );
  }

  /// Create a copy with additional attachments
  ChatMessage withAttachments(List<FileAttachment> newAttachments) {
    return copyWith(
      attachments: [...attachments, ...newAttachments],
    );
  }

  /// Create a copy with attachments parsed from file references
  ChatMessage withFileReferences(List<FileAttachment> fileAttachments) {
    return copyWith(
      attachments: [...attachments, ...fileAttachments],
    );
  }

  @override
  String toString() {
    return 'ChatMessage(id: $id, role: $role, content: ${content.length} chars, '
           'attachments: ${attachments.length})';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is ChatMessage &&
        other.id == id &&
        other.content == content &&
        other.role == role &&
        other.timestamp == timestamp &&
        other.attachments.length == attachments.length &&
        other.isStreaming == isStreaming;
  }

  @override
  int get hashCode {
    return Object.hash(id, content, role, timestamp, attachments.length, isStreaming);
  }
}

