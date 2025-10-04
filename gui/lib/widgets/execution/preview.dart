import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:gui/core/config.dart';
import 'package:gui/data/services/streaming_service.dart';
import 'package:gui/data/models/file_attachment.dart';
import 'package:gui/widgets/previews/file_preview.dart';
import 'package:http/http.dart' as http;

/// Types of preview content
enum PreviewType {
  image,
  audio,
  text,
  none,
}

/// Preview data container
class PreviewData {
  final PreviewType type;
  final String content; // URL or text content
  final String? filename;

  const PreviewData({
    required this.type,
    required this.content,
    this.filename,
  });

  PreviewData copyWith({
    PreviewType? type,
    String? content,
    String? filename,
  }) {
    return PreviewData(
      type: type ?? this.type,
      content: content ?? this.content,
      filename: filename ?? this.filename,
    );
  }
}

/// Preview widget that displays different types of output files
class Preview extends StatefulWidget {
  final StreamingService? streamingService;
  final String? executionOutputPath;
  final String? lastSavedFile;
  final String? currentConversationId;
  final int? currentStepIndex;
  final String? currentToolName;
  final List<String>? chosenPath;
  final List<dynamic>? messages;
  final Map<int, dynamic>? lastFileByStep;

  const Preview({
    Key? key,
    this.streamingService,
    this.executionOutputPath,
    this.lastSavedFile,
    this.currentConversationId,
    this.currentStepIndex,
    this.currentToolName,
    this.chosenPath,
    this.messages,
    this.lastFileByStep,
  }) : super(key: key);

  @override
  State<Preview> createState() => _PreviewState();
}

class _PreviewState extends State<Preview> {
  PreviewData _previewData = const PreviewData(type: PreviewType.none, content: '');
  String _textContent = '';
  bool _textLoading = false;
  String _textError = '';
  bool _isLoading = false;
  
  // Stream subscription
  StreamSubscription<ExecutorStepData>? _stepSubscription;

  @override
  void initState() {
    super.initState();
    _setupStreamingListeners();
    _loadPreview();
  }

  @override
  void didUpdateWidget(Preview oldWidget) {
    super.didUpdateWidget(oldWidget);
    
    if (widget.streamingService != oldWidget.streamingService) {
      _setupStreamingListeners();
    }
    
    if (widget.currentStepIndex != oldWidget.currentStepIndex ||
        widget.currentToolName != oldWidget.currentToolName ||
        widget.lastSavedFile != oldWidget.lastSavedFile ||
        widget.executionOutputPath != oldWidget.executionOutputPath) {
      _loadPreview();
    }
  }
  
  @override
  void dispose() {
    _stepSubscription?.cancel();
    super.dispose();
  }
  
  /// Setup streaming listeners for executor step events
  void _setupStreamingListeners() {
    _stepSubscription?.cancel();
    
    if (widget.streamingService != null) {
      _stepSubscription = widget.streamingService!.executorSteps.listen((stepData) {
        // On tool end, try to load preview from its workspace directory
        if (stepData.status == 'end' && stepData.workspaceDir != null) {
          _loadPreviewFromWorkspaceDir(stepData.workspaceDir!, stepData.toolName, stepData.stepIndex);
        }
      });
    }
  }
  
  /// Load preview from workspace directory after tool completion
  Future<void> _loadPreviewFromWorkspaceDir(String workspaceDir, String toolName, int stepIndex) async {
    try {
      final executionOutputPath = _getExecutionOutputPath();
      if (executionOutputPath == null) return;
      
      // Strip Docker path prefix to get relative path
      final relativePath = executionOutputPath
          .replaceAll('\\', '/')
          .replaceFirst(RegExp(r'^/app/outputs/'), '')
          .replaceFirst(RegExp(r'^outputs/'), '');
      
      // List files in outputs directory
      final files = await _listOutputFilesFromPath(relativePath);
      if (files.isEmpty) return;
      
      // Filter files that match this step
      final stepPrefix = '${stepIndex.toString().padLeft(2, '0')}_$toolName';
      final matchingFiles = files.where((f) {
        final filename = (f['filename']?.toString() ?? '').toLowerCase();
        return filename.startsWith(stepPrefix.toLowerCase()) && !_isLogFile(filename);
      }).toList();
      
      if (matchingFiles.isEmpty) return;
      
      // Pick the first matching file
      final file = matchingFiles.first;
      final filename = file['filename']?.toString() ?? '';
      final mimeType = file['mime_type']?.toString() ?? '';
      
      // Build URL
      final fullPath = '$relativePath/$filename';
      final url = AppConfig.api('/artifacts/outputs/file', {'path': fullPath}).toString();
      final type = _determinePreviewType(filename, mimeType);
      
      setState(() {
        _previewData = PreviewData(
          type: type,
          content: url,
          filename: filename,
        );
        _isLoading = false;
      });
    } catch (e) {
      // Silently fail - fallback to existing preview
    }
  }

  /// Load preview content based on current context
  Future<void> _loadPreview() async {
    debugPrint('🖼️ [PREVIEW] _loadPreview called');
    debugPrint('🖼️ [PREVIEW] currentToolName: ${widget.currentToolName}');
    debugPrint('🖼️ [PREVIEW] currentStepIndex: ${widget.currentStepIndex}');
    debugPrint('🖼️ [PREVIEW] chatId: ${widget.currentConversationId}');
    
    setState(() {
      _isLoading = true;
    });

    try {
      // Priority: per-step file, then list outputs, then lastSavedFile, then execution_output_path
      debugPrint('🖼️ [PREVIEW] Trying _loadFromStepFile...');
      if (await _loadFromStepFile()) {
        debugPrint('🖼️ [PREVIEW] ✅ Loaded from step file');
        return;
      }
      
      debugPrint('🖼️ [PREVIEW] Trying _loadFromOutputs...');
      if (await _loadFromOutputs()) {
        debugPrint('🖼️ [PREVIEW] ✅ Loaded from outputs');
        return;
      }
      
      debugPrint('🖼️ [PREVIEW] Trying _loadFromSavedFile...');
      if (await _loadFromSavedFile()) {
        debugPrint('🖼️ [PREVIEW] ✅ Loaded from saved file');
        return;
      }
      
      debugPrint('🖼️ [PREVIEW] Trying _loadFromExecutionPath...');
      if (await _loadFromExecutionPath()) {
        debugPrint('🖼️ [PREVIEW] ✅ Loaded from execution path');
        return;
      }
      
      // No preview available
      debugPrint('🖼️ [PREVIEW] ❌ No preview available');
      setState(() {
        _previewData = const PreviewData(type: PreviewType.none, content: '');
        _isLoading = false;
      });
    } catch (e) {
      debugPrint('🖼️ [PREVIEW] ❌ Error loading preview: $e');
      setState(() {
        _previewData = const PreviewData(type: PreviewType.none, content: '');
        _isLoading = false;
      });
    }
  }

  /// Load preview from step-specific file
  Future<bool> _loadFromStepFile() async {
    if (widget.currentStepIndex == null || widget.lastFileByStep == null) return false;
    
    final stepFile = widget.lastFileByStep![widget.currentStepIndex!];
    if (stepFile == null || stepFile['path'] == null) return false;
    
    final path = stepFile['path'].toString();
    final mime = stepFile['mime']?.toString() ?? '';
    final filename = path.split('/').last;
    
    final url = _resolveFileUrl(path);
    final type = _determinePreviewType(filename, mime);
    
    setState(() {
      _previewData = PreviewData(
        type: type,
        content: url,
        filename: filename,
      );
      _isLoading = false;
    });
    
    return true;
  }

  /// Load preview from outputs directory
  Future<bool> _loadFromOutputs() async {
    final executionOutputPath = _getExecutionOutputPath();
    
    if (executionOutputPath == null) {
      debugPrint('🖼️ [PREVIEW] _loadFromOutputs - No execution_output_path, returning false');
      return false;
    }
    
    try {
      // Strip Docker path prefix to get relative path for API
      // /app/outputs/chat_id/msg_id -> chat_id/msg_id
      final relativePath = executionOutputPath
          .replaceAll('\\', '/')
          .replaceFirst(RegExp(r'^/app/outputs/'), '')
          .replaceFirst(RegExp(r'^outputs/'), '');
      
      debugPrint('🖼️ [PREVIEW] _loadFromOutputs - Relative path: $relativePath');
      
      final files = await _listOutputFilesFromPath(relativePath);
      debugPrint('🖼️ [PREVIEW] _loadFromOutputs - Found ${files.length} files');
      
      if (files.isEmpty) {
        debugPrint('🖼️ [PREVIEW] _loadFromOutputs - No files found');
        return false;
      }
      
      return await _selectBestFile(files, relativePath);
    } catch (e) {
      debugPrint('🖼️ [PREVIEW] _loadFromOutputs - Error: $e');
      return false;
    }
  }

  /// Load preview from last saved file
  Future<bool> _loadFromSavedFile() async {
    if (widget.lastSavedFile == null) return false;
    
    final path = widget.lastSavedFile!;
    final filename = path.split('/').last;
    final url = _resolveFileUrl(path);
    final type = _determinePreviewType(filename, '');
    
    setState(() {
      _previewData = PreviewData(
        type: type,
        content: url,
        filename: filename,
      );
      _isLoading = false;
    });
    
    return true;
  }

  /// Load preview from execution output path
  Future<bool> _loadFromExecutionPath() async {
    final execPath = widget.executionOutputPath;
    if (execPath == null) return false;
    
    final filename = execPath.split('/').last;
    final url = _resolveFileUrl(execPath);
    final type = _determinePreviewType(filename, '');
    
    setState(() {
      _previewData = PreviewData(
        type: type,
        content: url,
        filename: filename,
      );
      _isLoading = false;
    });
    
    return true;
  }

  /// List output files from a relative path (e.g., "chat_id/msg_id")
  Future<List<Map<String, dynamic>>> _listOutputFilesFromPath(String relativePath) async {
    // Extract chat_id from path to call artifacts endpoint
    final parts = relativePath.split('/');
    if (parts.isEmpty) return [];
    
    final convId = parts[0];
    final url = AppConfig.api('/artifacts/${Uri.encodeComponent(convId)}');
    debugPrint('🖼️ [PREVIEW] ========================================');
    debugPrint('🖼️ [PREVIEW] 🌐 API URL: $url');
    debugPrint('🖼️ [PREVIEW] 📂 Looking for files in: $relativePath/');
    debugPrint('🖼️ [PREVIEW] ========================================');
    
    final response = await http.get(url);
    debugPrint('🖼️ [PREVIEW] Response status: ${response.statusCode}');
    
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      final files = data['files'] as List?;
      debugPrint('🖼️ [PREVIEW] Total files in response: ${files?.length ?? 0}');
      
      if (files != null) {
        // Filter files to only those in the specified path
        final filtered = files.cast<Map<String, dynamic>>()
          .where((file) {
            final fileRelPath = file['relative_path']?.toString() ?? '';
            // Check if file is in this output folder
            return fileRelPath.startsWith('$relativePath/');
          })
          .toList();
        
        debugPrint('🖼️ [PREVIEW] Filtered ${filtered.length} files for $relativePath/');
        for (final file in filtered) {
          debugPrint('🖼️ [PREVIEW]   - ${file['filename']} (${file['mime_type']})');
        }
        return filtered;
      }
    }
    
    debugPrint('🖼️ [PREVIEW] No files found, returning empty list');
    return [];
  }

  /// Select the best file for preview
  Future<bool> _selectBestFile(List<Map<String, dynamic>> files, String relativePath) async {
    if (files.isEmpty) return false;
    
    // Filter out log files
    final nonLogFiles = files.where((f) => !_isLogFile(f['filename']?.toString() ?? '')).toList();
    if (nonLogFiles.isEmpty) return false;
    
    // Score files based on step matching
    final stepPrefix = _deriveStepPrefix();
    
    int scoreFile(Map<String, dynamic> file) {
      final filename = (file['filename']?.toString() ?? '').toLowerCase();
      if (stepPrefix != null && filename.startsWith(stepPrefix.toLowerCase())) return 3;
      if (widget.currentStepIndex != null) {
        final stepStr = widget.currentStepIndex!.toString().padLeft(2, '0');
        if (filename.startsWith('${stepStr}_')) return 2;
      }
      return 1;
    }
    
    // Sort by score and pick the best
    nonLogFiles.sort((a, b) => scoreFile(b).compareTo(scoreFile(a)));
    final bestFile = nonLogFiles.first;
    
    final filename = bestFile['filename']?.toString() ?? '';
    final mimeType = bestFile['mime_type']?.toString() ?? '';
    
    // Build URL using relative path and filename
    final fullPath = '$relativePath/$filename';
    final url = AppConfig.api('/artifacts/outputs/file', {'path': fullPath}).toString();
    debugPrint('🖼️ [PREVIEW] Selected file: $filename, URL: $url');
    
    final type = _determinePreviewType(filename, mimeType);
    
    setState(() {
      _previewData = PreviewData(
        type: type,
        content: url,
        filename: filename,
      );
      _isLoading = false;
    });
    
    return true;
  }

  /// Check if file is a log file
  bool _isLogFile(String filename) {
    return filename.toLowerCase().endsWith('.log') ||
           filename.toLowerCase().contains('stdout') ||
           filename.toLowerCase().contains('stderr');
  }

  /// Derive conversation and message IDs
  /// Get the execution output path (directory containing all step outputs)
  String? _getExecutionOutputPath() {
    debugPrint('🖼️ [PREVIEW] execution_output_path: ${widget.executionOutputPath}');
    return widget.executionOutputPath;
  }

  /// Derive step prefix for file matching
  String? _deriveStepPrefix() {
    String? tool = widget.currentToolName;
    
    if (tool == null && 
        widget.currentStepIndex != null && 
        widget.chosenPath != null &&
        widget.currentStepIndex! >= 0 &&
        widget.currentStepIndex! < widget.chosenPath!.length) {
      final nodeId = widget.chosenPath![widget.currentStepIndex!];
      if (!_isEndpointNode(nodeId)) {
        tool = nodeId;
      }
    }
    
    if (widget.currentStepIndex != null && tool != null) {
      final num = widget.currentStepIndex!.toString().padLeft(2, '0');
      return '${num}_$tool';
    }
    
    return null;
  }

  /// Check if node is an endpoint
  bool _isEndpointNode(String nodeId) {
    return nodeId.endsWith('_IN') || nodeId.endsWith('_OUT');
  }

  /// Resolve file URL
  String _resolveFileUrl(String path) {
    debugPrint('🖼️ [PREVIEW] _resolveFileUrl input: $path');
    
    if (path.startsWith('http')) {
      debugPrint('🖼️ [PREVIEW] Already HTTP URL, returning as-is');
      return path;
    }
    
    final norm = path.replaceAll('\\', '/');
    String rel = norm;
    String url;
    
    // Strip Docker container path prefix if present (e.g., /app/inputs/... or /app/outputs/...)
    if (norm.startsWith('/app/inputs/')) {
      rel = norm.substring('/app/inputs/'.length);
      // inputs use chat_id/file/filename pattern
      final parts = rel.split('/');
      if (parts.length >= 2) {
        final chatId = parts[0];
        final filename = parts.last;
        url = AppConfig.api('/artifacts/${Uri.encodeComponent(chatId)}/file/${Uri.encodeComponent(filename)}').toString();
        debugPrint('🖼️ [PREVIEW] Matched /app/inputs/ → $url');
        return url;
      }
    } else if (norm.startsWith('/app/outputs/')) {
      rel = norm.substring('/app/outputs/'.length);
      url = AppConfig.api('/artifacts/outputs/file', {'path': rel}).toString();
      debugPrint('🖼️ [PREVIEW] Matched /app/outputs/ → $url');
      return url;
    } else if (norm.contains('/outputs/')) {
      rel = norm.split('/outputs/').last;
      url = AppConfig.api('/artifacts/outputs/file', {'path': rel}).toString();
      debugPrint('🖼️ [PREVIEW] Matched /outputs/ → $url');
      return url;
    } else if (norm.startsWith('outputs/')) {
      rel = norm.substring('outputs/'.length);
      url = AppConfig.api('/artifacts/outputs/file', {'path': rel}).toString();
      debugPrint('🖼️ [PREVIEW] Matched outputs/ → $url');
      return url;
    } else if (norm.contains('/inputs/')) {
      rel = norm.split('/inputs/').last;
      // inputs use chat_id/file/filename pattern
      final parts = rel.split('/');
      if (parts.length >= 2) {
        final chatId = parts[0];
        final filename = parts.last;
        url = AppConfig.api('/artifacts/${Uri.encodeComponent(chatId)}/file/${Uri.encodeComponent(filename)}').toString();
        debugPrint('🖼️ [PREVIEW] Matched /inputs/ → $url');
        return url;
      }
    } else if (norm.startsWith('inputs/')) {
      rel = norm.substring('inputs/'.length);
      // inputs use chat_id/file/filename pattern
      final parts = rel.split('/');
      if (parts.length >= 2) {
        final chatId = parts[0];
        final filename = parts.last;
        url = AppConfig.api('/artifacts/${Uri.encodeComponent(chatId)}/file/${Uri.encodeComponent(filename)}').toString();
        debugPrint('🖼️ [PREVIEW] Matched inputs/ → $url');
        return url;
      }
    }
    
    // Default to outputs
    url = AppConfig.api('/artifacts/outputs/file', {'path': rel}).toString();
    debugPrint('🖼️ [PREVIEW] Default fallback → $url');
    return url;
  }

  /// Determine preview type from filename and MIME type
  PreviewType _determinePreviewType(String filename, String mimeType) {
    final lower = filename.toLowerCase();
    
    if (mimeType.startsWith('image/') || 
        RegExp(r'\.(png|jpg|jpeg|gif|webp)$').hasMatch(lower)) {
      return PreviewType.image;
    }
    
    if (mimeType.startsWith('audio/') || 
        RegExp(r'\.(mp3|wav|m4a|ogg)$').hasMatch(lower)) {
      return PreviewType.audio;
    }
    
    return PreviewType.text;
  }

  /// Load text content from URL
  Future<void> _loadTextContent() async {
    if (_previewData.type != PreviewType.text) return;
    
    setState(() {
      _textLoading = true;
      _textError = '';
    });
    
    try {
      final response = await http.get(Uri.parse(_previewData.content));
      
      if (response.statusCode == 200) {
        setState(() {
          _textContent = response.body;
          _textLoading = false;
        });
      } else {
        setState(() {
          _textContent = '';
          _textError = 'Failed to load (${response.statusCode})';
          _textLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        _textContent = '';
        _textError = 'Failed to load text';
        _textLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    // Load text content when preview data changes to text type
    if (_previewData.type == PreviewType.text && _textContent.isEmpty && !_textLoading && _textError.isEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _loadTextContent());
    }

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(
        children: [
          _buildHeader(),
          Expanded(
            child: _buildContent(),
          ),
        ],
      ),
    );
  }

  /// Build header with preview info
  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: const BoxDecoration(
        color: Color(0xFFF9FAFB),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(12),
          topRight: Radius.circular(12),
        ),
        border: Border(
          bottom: BorderSide(color: Color(0xFFE5E7EB)),
        ),
      ),
      child: Row(
        children: [
          // Status indicator
          Container(
            width: 8,
            height: 8,
            decoration: const BoxDecoration(
              color: Color(0xFF3B82F6),
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 8),
          const Text(
            'Preview',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
              color: Color(0xFF374151),
            ),
          ),
          const Spacer(),
          // Preview type and filename
          Row(
            children: [
              Text(
                _previewData.type.name,
                style: const TextStyle(
                  fontSize: 11,
                  color: Color(0xFF6B7280),
                ),
              ),
              if (_previewData.filename != null) ...[
                const Text(
                  ' • ',
                  style: TextStyle(
                    fontSize: 11,
                    color: Color(0xFF9CA3AF),
                  ),
                ),
                Text(
                  _previewData.filename!,
                  style: const TextStyle(
                    fontSize: 11,
                    color: Color(0xFF9CA3AF),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  /// Build main content area
  Widget _buildContent() {
    if (_isLoading) {
      return const Center(
        child: CircularProgressIndicator(),
      );
    }

    // Convert PreviewData to FileAttachment and use FilePreview for consistency
    if (_previewData.type != PreviewType.none && _previewData.type != PreviewType.text) {
      final attachment = _previewDataToAttachment(_previewData);
      return Container(
        width: double.infinity,
        height: double.infinity,
        color: const Color(0xFFF9FAFB),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 800),
            child: FilePreview(
              attachment: attachment,
              isCompact: false,
            ),
          ),
        ),
      );
    }

    switch (_previewData.type) {
      case PreviewType.text:
        return _buildTextPreview();
      case PreviewType.none:
        return _buildNoPreview();
      default:
        return _buildNoPreview();
    }
  }

  /// Convert PreviewData to FileAttachment for use with FilePreview widget
  FileAttachment _previewDataToAttachment(PreviewData data) {
    // Determine MIME type from PreviewType and filename
    String mimeType = 'application/octet-stream';
    if (data.type == PreviewType.image) {
      mimeType = 'image/${data.filename?.split('.').last ?? 'png'}';
    } else if (data.type == PreviewType.audio) {
      mimeType = 'audio/${data.filename?.split('.').last ?? 'wav'}';
    }

    return FileAttachment(
      filename: data.filename ?? 'unknown',
      url: data.content,
      mimeType: mimeType,
    );
  }

  /// Build text preview
  Widget _buildTextPreview() {
    if (_textLoading) {
      return const Center(
        child: CircularProgressIndicator(),
      );
    }
    
    if (_textError.isNotEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.error_outline,
              color: Color(0xFFEF4444),
              size: 48,
            ),
            const SizedBox(height: 16),
            Text(
              _textError,
              style: const TextStyle(
                color: Color(0xFFEF4444),
                fontSize: 14,
              ),
            ),
          ],
        ),
      );
    }
    
    return Container(
      width: double.infinity,
      height: double.infinity,
      padding: const EdgeInsets.all(16),
      child: SingleChildScrollView(
        child: SelectableText(
          _textContent,
          style: const TextStyle(
            fontSize: 13,
            color: Color(0xFF374151),
            fontFamily: 'Courier',
            height: 1.4,
          ),
        ),
      ),
    );
  }

  /// Build no preview available state
  Widget _buildNoPreview() {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: const Color(0xFFF9FAFB),
      child: const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.description_outlined,
              color: Color(0xFF6B7280),
              size: 48,
            ),
            SizedBox(height: 16),
            Text(
              'No Preview Available',
              style: TextStyle(
                color: Color(0xFF374151),
                fontSize: 16,
                fontWeight: FontWeight.w500,
              ),
            ),
            SizedBox(height: 8),
            Text(
              'Output will appear here',
              style: TextStyle(
                color: Color(0xFF6B7280),
                fontSize: 14,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
