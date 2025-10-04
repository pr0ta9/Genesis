import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';
import 'package:gui/core/config.dart';
import 'package:gui/data/models/file_attachment.dart';

/// Service for handling file uploads and artifact management via API
class ArtifactService {
  final http.Client _client = http.Client();

  /// Pick multiple files from device storage
  Future<List<File>> pickFiles({
    FileType type = FileType.any,
    List<String>? allowedExtensions,
    bool allowMultiple = true,
  }) async {
    try {
      FilePickerResult? result = await FilePicker.platform.pickFiles(
        type: type,
        allowedExtensions: allowedExtensions,
        allowMultiple: allowMultiple,
        withData: false, // We'll read the file data ourselves
        withReadStream: false,
      );

      if (result != null && result.files.isNotEmpty) {
        List<File> files = [];
        for (PlatformFile platformFile in result.files) {
          if (platformFile.path != null) {
            files.add(File(platformFile.path!));
          }
        }
        return files;
      }
      return [];
    } catch (e) {
      debugPrint('❌ File picker error: $e');
      return [];
    }
  }

  /// Upload files to the artifacts API
  Future<ArtifactUploadResponse?> uploadFiles(String chatId, List<File> files) async {
    if (files.isEmpty) return null;

    try {
      debugPrint('🚀 Uploading ${files.length} files to chat: $chatId');
      
      final uri = AppConfig.api('/artifacts/$chatId/upload');
      final request = http.MultipartRequest('POST', uri);

      // Add files to the request
      for (File file in files) {
        if (await file.exists()) {
          final filename = file.path.split('/').last;
          final fileBytes = await file.readAsBytes();
          
          request.files.add(
            http.MultipartFile.fromBytes(
              'files', // Field name expected by FastAPI
              fileBytes,
              filename: filename,
            ),
          );
          debugPrint('📁 Added file: $filename (${fileBytes.length} bytes)');
        }
      }

      // Send the request
      final response = await _client.send(request);
      final responseBody = await response.stream.bytesToString();

      if (response.statusCode == 200) {
        final jsonData = jsonDecode(responseBody) as Map<String, dynamic>;
        final uploadResponse = ArtifactUploadResponse.fromJson(jsonData);
        debugPrint('✅ Upload successful: ${uploadResponse.count} files uploaded');
        return uploadResponse;
      } else {
        debugPrint('❌ Upload failed: ${response.statusCode} - $responseBody');
        throw Exception('Upload failed: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('❌ Upload error: $e');
      return null;
    }
  }

  /// List artifacts for a specific chat
  Future<ArtifactListResponse?> listArtifacts(String chatId) async {
    try {
      debugPrint('📋 Listing artifacts for chat: $chatId');
      
      final uri = AppConfig.api('/artifacts/$chatId');
      final response = await _client.get(uri);

      if (response.statusCode == 200) {
        final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
        final listResponse = ArtifactListResponse.fromJson(jsonData);
        debugPrint('✅ Found ${listResponse.count} artifacts');
        return listResponse;
      } else if (response.statusCode == 404) {
        // No artifacts found - return empty response
        return const ArtifactListResponse(files: [], count: 0);
      } else {
        debugPrint('❌ List artifacts failed: ${response.statusCode} - ${response.body}');
        throw Exception('Failed to list artifacts: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('❌ List artifacts error: $e');
      return null;
    }
  }

  /// Create FileAttachment objects from selected platform files
  List<FileAttachment> createAttachmentsFromFiles(List<File> files) {
    return files.map((file) {
      final filename = file.path.split('/').last;
      final mimeType = _getMimeType(filename);
      
      return FileAttachment(
        filename: filename,
        path: file.path,
        mimeType: mimeType,
        size: file.lengthSync(),
        uploadedAt: DateTime.now(),
      );
    }).toList();
  }

  /// Get MIME type from file extension
  String _getMimeType(String filename) {
    final ext = filename.toLowerCase().split('.').last;
    
    switch (ext) {
      // Images
      case 'png':
        return 'image/png';
      case 'jpg':
      case 'jpeg':
        return 'image/jpeg';
      case 'gif':
        return 'image/gif';
      case 'webp':
        return 'image/webp';
      case 'svg':
        return 'image/svg+xml';
      
      // Audio
      case 'mp3':
        return 'audio/mpeg';
      case 'wav':
        return 'audio/wav';
      case 'm4a':
        return 'audio/mp4';
      case 'ogg':
        return 'audio/ogg';
      case 'flac':
        return 'audio/flac';
      case 'webm':
        return 'audio/webm';
      
      // Video
      case 'mp4':
        return 'video/mp4';
      case 'mov':
        return 'video/quicktime';
      case 'avi':
        return 'video/x-msvideo';
      
      // Documents
      case 'txt':
        return 'text/plain';
      case 'pdf':
        return 'application/pdf';
      case 'doc':
        return 'application/msword';
      case 'docx':
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      case 'json':
        return 'application/json';
      case 'xml':
        return 'application/xml';
      case 'csv':
        return 'text/csv';
      
      default:
        return 'application/octet-stream';
    }
  }

  /// Extract file references from assistant message content (from <file> tags)
  List<String> extractFileReferences(String content) {
    final regex = RegExp(r'<file>([\s\S]*?)<\/file>', caseSensitive: false);
    final matches = regex.allMatches(content);
    
    return matches
        .map((match) => match.group(1)?.trim())
        .where((path) => path != null && path.isNotEmpty)
        .cast<String>()
        .toList();
  }

  /// Convert file reference paths to FileAttachment objects
  List<FileAttachment> createAttachmentsFromReferences(List<String> references) {
    return references.map((ref) {
      final filename = ref.split('/').last;
      final mimeType = _getMimeType(filename);
      
      return FileAttachment(
        filename: filename,
        path: ref,
        mimeType: mimeType,
      );
    }).toList();
  }

  /// Validate file before upload
  bool validateFile(File file, {int maxSizeBytes = 50 * 1024 * 1024}) { // 50MB default
    try {
      if (!file.existsSync()) {
        debugPrint('❌ File does not exist: ${file.path}');
        return false;
      }

      final size = file.lengthSync();
      if (size > maxSizeBytes) {
        debugPrint('❌ File too large: ${size} bytes (max: ${maxSizeBytes})');
        return false;
      }

      final filename = file.path.split('/').last;
      if (filename.isEmpty) {
        debugPrint('❌ Invalid filename: ${file.path}');
        return false;
      }

      return true;
    } catch (e) {
      debugPrint('❌ File validation error: $e');
      return false;
    }
  }

  /// Dispose of the service
  void dispose() {
    _client.close();
  }
}

