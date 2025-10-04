import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:gui/core/config.dart';
import 'package:gui/data/services/streaming_service.dart';
import 'package:http/http.dart' as http;

/// Represents a line in the terminal console
class TerminalLine {
  final int id;
  final String content;
  final TerminalLineType type;
  final DateTime timestamp;

  const TerminalLine({
    required this.id,
    required this.content,
    required this.type,
    required this.timestamp,
  });
}

/// Types of terminal lines
enum TerminalLineType {
  output,
  error,
  input,
}

/// Console widget that displays terminal-like output with auto-scrolling
class Console extends StatefulWidget {
  final StreamingService? streamingService;
  final int? currentStepIndex;
  final String? currentToolName;
  final List<String>? chosenPath;
  final String? executionOutputPath;
  final String? currentConversationId;
  final String? lastSavedFile;
  final List<dynamic>? messages;

  const Console({
    Key? key,
    this.streamingService,
    this.currentStepIndex,
    this.currentToolName,
    this.chosenPath,
    this.executionOutputPath,
    this.currentConversationId,
    this.lastSavedFile,
    this.messages,
  }) : super(key: key);

  @override
  State<Console> createState() => _ConsoleState();
}

class _ConsoleState extends State<Console> {
  final List<TerminalLine> _lines = [];
  final ScrollController _scrollController = ScrollController();
  int _nextId = 3;
  
  // Step log lines loaded from files
  final List<TerminalLine> _stepLogLines = [];
  
  // Stream subscriptions
  StreamSubscription<ConsoleEntry>? _consoleSubscription;

  @override
  void initState() {
    super.initState();
    
    // Initialize with welcome messages
    _lines.addAll([
      TerminalLine(
        id: 1,
        content: 'Genesis Terminal v1.0.0',
        type: TerminalLineType.output,
        timestamp: DateTime.now(),
      ),
      TerminalLine(
        id: 2,
        content: 'Ready for execution...',
        type: TerminalLineType.output,
        timestamp: DateTime.now(),
      ),
    ]);
    
    // Setup streaming listeners
    _setupStreamingListeners();
    
    // Load initial logs
    _loadStepLogs();
  }

  @override
  void didUpdateWidget(Console oldWidget) {
    super.didUpdateWidget(oldWidget);
    
    // Setup streaming if service changed
    if (widget.streamingService != oldWidget.streamingService) {
      _setupStreamingListeners();
    }
    
    // Reload step logs if context changes
    if (widget.currentStepIndex != oldWidget.currentStepIndex ||
        widget.currentToolName != oldWidget.currentToolName ||
        widget.executionOutputPath != oldWidget.executionOutputPath) {
      _loadStepLogs();
    }
  }

  @override
  void dispose() {
    _consoleSubscription?.cancel();
    _scrollController.dispose();
    super.dispose();
  }
  
  /// Setup streaming listeners for live console output
  void _setupStreamingListeners() {
    _consoleSubscription?.cancel();
    
    if (widget.streamingService != null) {
      _consoleSubscription = widget.streamingService!.consoleOutput.listen((entry) {
        _addConsoleEntry(entry);
      });
    }
  }
  
  /// Add a single console entry from stream
  void _addConsoleEntry(ConsoleEntry entry) {
    setState(() {
      _processConsoleEntry(entry);
    });
    _scrollToBottom();
  }

  /// Process a single console entry
  void _processConsoleEntry(ConsoleEntry entry) {
    final type = entry.type == 'stderr' ? TerminalLineType.error : TerminalLineType.output;
    final content = entry.line;
    final timestamp = DateTime.tryParse(entry.timestamp) ?? DateTime.now();
    
    // Check if line references an output file
    final fileMatch = RegExp(r'(?:^|\s)(outputs\/[\w\-\/\.]+\.(?:txt|log))(?:\s|$)', 
        caseSensitive: false).firstMatch(content);
    
    if (fileMatch != null) {
      final filePath = fileMatch.group(1)!;
      _expandFileContent(filePath, timestamp, type);
    } else {
      // Add regular line
      _lines.add(TerminalLine(
        id: _nextId++,
        content: content,
        type: type,
        timestamp: timestamp,
      ));
    }
  }

  /// Expand file content inline in console
  Future<void> _expandFileContent(String filePath, DateTime timestamp, TerminalLineType type) async {
    try {
      final url = _resolveOutputUrl(filePath);
      final response = await http.get(Uri.parse(url));
      
      if (response.statusCode == 200) {
        final content = response.body;
        
        // Add file header
        _lines.add(TerminalLine(
          id: _nextId++,
          content: '--- $filePath ---',
          type: TerminalLineType.output,
          timestamp: timestamp,
        ));
        
        // Add file content lines
        final contentLines = content.split('\n');
        for (final line in contentLines) {
          if (line.trim().isNotEmpty) {
            _lines.add(TerminalLine(
              id: _nextId++,
              content: line,
              type: type,
              timestamp: timestamp,
            ));
          }
        }
      } else {
        // Just add the original line if file can't be expanded
        _lines.add(TerminalLine(
          id: _nextId++,
          content: filePath,
          type: type,
          timestamp: timestamp,
        ));
      }
    } catch (e) {
      // Just add the original line if there's an error
      _lines.add(TerminalLine(
        id: _nextId++,
        content: filePath,
        type: type,
        timestamp: timestamp,
      ));
    }
  }

  /// Load stdout/stderr logs for the current step
  Future<void> _loadStepLogs() async {
    debugPrint('📋 [CONSOLE] _loadStepLogs called');
    debugPrint('📋 [CONSOLE] currentToolName: ${widget.currentToolName}');
    debugPrint('📋 [CONSOLE] currentStepIndex: ${widget.currentStepIndex}');
    
    // Skip if we have recent streaming activity
    if (widget.streamingService != null) {
      final entries = widget.streamingService!.currentConsoleEntries;
      debugPrint('📋 [CONSOLE] Streaming entries count: ${entries.length}');
      if (entries.isNotEmpty) {
        final now = DateTime.now();
        final hasRecentStream = entries.any((entry) {
          final timestamp = DateTime.tryParse(entry.timestamp) ?? now;
          final diff = now.difference(timestamp).inMilliseconds;
          return diff < 2000; // 2 second threshold
        });
        
        if (hasRecentStream) {
          debugPrint('📋 [CONSOLE] Has recent streaming activity, skipping file load');
          setState(() {
            _stepLogLines.clear();
          });
          return;
        }
      }
    }
    
    final executionOutputPath = _getExecutionOutputPath();
    if (executionOutputPath == null) {
      debugPrint('📋 [CONSOLE] No execution_output_path, clearing logs');
      setState(() {
        _stepLogLines.clear();
      });
      return;
    }
    
    try {
      // Strip Docker path prefix to get relative path for API
      // /app/outputs/chat_id/msg_id -> chat_id/msg_id
      final relativePath = executionOutputPath
          .replaceAll('\\', '/')
          .replaceFirst(RegExp(r'^/app/outputs/'), '')
          .replaceFirst(RegExp(r'^outputs/'), '');
      
      debugPrint('📋 [CONSOLE] Relative output path: $relativePath');
      
      // List all files in this output directory
      final files = await _listOutputFilesFromPath(relativePath);
      debugPrint('📋 [CONSOLE] Found ${files.length} output files');
      
      final stepPrefix = _deriveStepPrefix();
      debugPrint('📋 [CONSOLE] Step prefix: $stepPrefix');
      
      // Find best matching stdout/stderr files
      final stdoutFile = _findBestLogFile(files, stepPrefix, 'stdout.log');
      final stderrFile = _findBestLogFile(files, stepPrefix, 'stderr.log');
      
      debugPrint('📋 [CONSOLE] Found stdout: ${stdoutFile?['filename']}');
      debugPrint('📋 [CONSOLE] Found stderr: ${stderrFile?['filename']}');
      
      final List<TerminalLine> stepLines = [];
      
      // Load stdout first, then stderr if needed
      final hasLiveStderr = widget.streamingService?.currentConsoleEntries.any((e) => e.type == 'stderr') ?? false;
      
      if (hasLiveStderr && stderrFile != null) {
        debugPrint('📋 [CONSOLE] Loading stderr (has live errors)');
        final url = _buildOutputFileUrl(relativePath, stderrFile['filename']!);
        await _loadLogFileFromUrl(url, TerminalLineType.error, stepLines);
      } else if (stdoutFile != null) {
        debugPrint('📋 [CONSOLE] Loading stdout');
        final url = _buildOutputFileUrl(relativePath, stdoutFile['filename']!);
        await _loadLogFileFromUrl(url, TerminalLineType.output, stepLines);
      } else if (stderrFile != null) {
        debugPrint('📋 [CONSOLE] Loading stderr (fallback)');
        final url = _buildOutputFileUrl(relativePath, stderrFile['filename']!);
        await _loadLogFileFromUrl(url, TerminalLineType.error, stepLines);
      }
      
      debugPrint('📋 [CONSOLE] Loaded ${stepLines.length} log lines');
      
      setState(() {
        _stepLogLines.clear();
        _stepLogLines.addAll(stepLines);
      });
    } catch (e) {
      debugPrint('📋 [CONSOLE] Error loading logs: $e');
      setState(() {
        _stepLogLines.clear();
      });
    }
  }

  /// List output files from a relative path (e.g., "chat_id/msg_id")
  Future<List<Map<String, String>>> _listOutputFilesFromPath(String relativePath) async {
    // Extract chat_id from path to call artifacts endpoint
    final parts = relativePath.split('/');
    if (parts.isEmpty) return [];
    
    final convId = parts[0];
    final url = AppConfig.api('/artifacts/${Uri.encodeComponent(convId)}');
    debugPrint('📋 [CONSOLE] ========================================');
    debugPrint('📋 [CONSOLE] 🌐 API URL: $url');
    debugPrint('📋 [CONSOLE] 📂 Looking for files in: $relativePath/');
    debugPrint('📋 [CONSOLE] ========================================');
    
    final response = await http.get(url);
    debugPrint('📋 [CONSOLE] Response status: ${response.statusCode}');
    
    if (response.statusCode == 200) {
      final data = json.decode(response.body);
      final files = data['files'] as List?;
      debugPrint('📋 [CONSOLE] Total files in response: ${files?.length ?? 0}');
      
      if (files != null) {
        // Filter files to only those in the specified path
        final filtered = files.cast<Map<String, dynamic>>()
          .where((file) {
            final fileRelPath = file['relative_path']?.toString() ?? '';
            // Check if file is in this output folder
            return fileRelPath.startsWith('$relativePath/');
          })
          .map((file) => {
            'path': file['path']?.toString() ?? '',
            'filename': file['filename']?.toString() ?? '',
          }).toList();
        
        debugPrint('📋 [CONSOLE] Filtered ${filtered.length} files for $relativePath/');
        for (final file in filtered) {
          debugPrint('📋 [CONSOLE]   - ${file['filename']}');
        }
        return filtered;
      }
    }
    
    debugPrint('📋 [CONSOLE] No files found, returning empty list');
    return [];
  }
  
  /// Build output file URL from relative path and filename
  String _buildOutputFileUrl(String relativePath, String filename) {
    final fullPath = '$relativePath/$filename';
    final url = AppConfig.api('/artifacts/outputs/file', {'path': fullPath}).toString();
    debugPrint('📋 [CONSOLE] Built file URL: $url');
    return url;
  }
  
  /// Load log file from URL
  Future<void> _loadLogFileFromUrl(String url, TerminalLineType type, List<TerminalLine> lines) async {
    try {
      debugPrint('📋 [CONSOLE] Loading log from: $url');
      final response = await http.get(Uri.parse(url));
      
      if (response.statusCode == 200) {
        // Decode as UTF-8 to properly handle CJK characters
        final content = utf8.decode(response.bodyBytes);
        final logLines = content.split('\n');
        debugPrint('📋 [CONSOLE] Parsed ${logLines.length} lines from log');
        
        for (final line in logLines) {
          if (line.trim().isNotEmpty) {
            lines.add(TerminalLine(
              id: _nextId++,
              content: line,
              type: type,
              timestamp: DateTime.now(),
            ));
          }
        }
      } else {
        debugPrint('📋 [CONSOLE] Failed to load log: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('📋 [CONSOLE] Error loading log file: $e');
    }
  }

  /// Find the best matching log file
  Map<String, String>? _findBestLogFile(List<Map<String, String>> files, String? stepPrefix, String suffix) {
    if (files.isEmpty) return null;
    
    final target = suffix.toLowerCase();
    
    int scoreFile(String filename) {
      final name = filename.toLowerCase();
      if (stepPrefix != null && name == '${stepPrefix.toLowerCase()}_$target') return 3;
      if (stepPrefix != null && name.startsWith('${stepPrefix.toLowerCase()}_') && name.endsWith(target)) return 2;
      if (name.endsWith(target)) return 1;
      return 0;
    }
    
    final bestFile = files
        .where((file) => scoreFile(file['filename']!) > 0)
        .toList()
      ..sort((a, b) => scoreFile(b['filename']!).compareTo(scoreFile(a['filename']!)));
    
    return bestFile.isNotEmpty ? bestFile.first : null;
  }


  /// Get the execution output path (directory containing all step outputs)
  String? _getExecutionOutputPath() {
    debugPrint('📋 [CONSOLE] execution_output_path: ${widget.executionOutputPath}');
    return widget.executionOutputPath;
  }

  /// Derive step prefix for log file matching
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

  /// Resolve output file URL
  String _resolveOutputUrl(String relOrAbsPath) {
    debugPrint('📋 [CONSOLE] _resolveOutputUrl input: $relOrAbsPath');
    
    if (relOrAbsPath.startsWith('http')) {
      debugPrint('📋 [CONSOLE] Already HTTP URL, returning as-is');
      return relOrAbsPath;
    }
    
    final norm = relOrAbsPath.replaceAll('\\', '/');
    final rel = norm.contains('/outputs/') 
        ? norm.split('/outputs/').last 
        : norm;
    
    final url = AppConfig.api('/artifacts/outputs/file?path=${Uri.encodeComponent(rel)}').toString();
    debugPrint('📋 [CONSOLE] Resolved URL: $url');
    return url;
  }

  /// Auto-scroll to bottom
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  /// Get color for terminal line type
  Color _getLineColor(TerminalLineType type) {
    switch (type) {
      case TerminalLineType.error:
        return const Color(0xFFFCA5A5); // red-300
      case TerminalLineType.input:
        return const Color(0xFF93C5FD); // blue-300
      case TerminalLineType.output:
        return const Color(0xFFD1D5DB); // gray-300
    }
  }

  /// Get prefix for terminal line type
  String _getLinePrefix(TerminalLineType type) {
    switch (type) {
      case TerminalLineType.input:
        return '> ';
      case TerminalLineType.error:
        return '! ';
      case TerminalLineType.output:
        return '  ';
    }
  }

  /// Copy all console content to clipboard
  void _copyToClipboard() {
    final allLines = [..._stepLogLines, ..._lines];
    final content = allLines.map((line) => 
        '${_getLinePrefix(line.type)}${line.content}').join('\n');
    
    if (content.isNotEmpty) {
      Clipboard.setData(ClipboardData(text: content));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Console output copied to clipboard'),
          duration: Duration(seconds: 2),
        ),
      );
    }
  }

  /// Clear console
  void _clearConsole() {
    setState(() {
      _lines.clear();
      _stepLogLines.clear();
      _nextId = 1;
      
      // Re-add welcome messages
      _lines.addAll([
        TerminalLine(
          id: _nextId++,
          content: 'Genesis Terminal v1.0.0',
          type: TerminalLineType.output,
          timestamp: DateTime.now(),
        ),
        TerminalLine(
          id: _nextId++,
          content: 'Ready for execution...',
          type: TerminalLineType.output,
          timestamp: DateTime.now(),
        ),
      ]);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.black,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE5E7EB)),
      ),
      child: Column(
        children: [
          _buildHeader(),
          Expanded(
            child: _buildTerminal(),
          ),
        ],
      ),
    );
  }

  /// Build console header
  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: const BoxDecoration(
        color: Color(0xFF1F2937),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(12),
          topRight: Radius.circular(12),
        ),
      ),
      child: Row(
        children: [
          // Terminal icon
          const Icon(
            Icons.terminal,
            color: Color(0xFF9CA3AF),
            size: 16,
          ),
          const SizedBox(width: 8),
          const Text(
            'Console',
            style: TextStyle(
              color: Color(0xFFD1D5DB),
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
          const Spacer(),
          // Action buttons
          IconButton(
            onPressed: _copyToClipboard,
            icon: const Icon(
              Icons.copy,
              color: Color(0xFF9CA3AF),
              size: 16,
            ),
            tooltip: 'Copy output',
            padding: const EdgeInsets.all(4),
            constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
          ),
          IconButton(
            onPressed: _clearConsole,
            icon: const Icon(
              Icons.clear,
              color: Color(0xFF9CA3AF),
              size: 16,
            ),
            tooltip: 'Clear console',
            padding: const EdgeInsets.all(4),
            constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
          ),
        ],
      ),
    );
  }

  /// Build terminal content
  Widget _buildTerminal() {
    final allLines = [..._stepLogLines, ..._lines];
    
    return Container(
      padding: const EdgeInsets.all(16),
      child: Scrollbar(
        controller: _scrollController,
        child: ListView.builder(
          controller: _scrollController,
          itemCount: allLines.length + 1, // +1 for cursor
          itemBuilder: (context, index) {
            if (index == allLines.length) {
              // Blinking cursor
              return Row(
                children: [
                  const Text(
                    '  ', // Prefix spacing
                    style: TextStyle(
                      color: Color(0xFF6B7280),
                      fontSize: 14,
                      fontFamily: 'Courier',
                    ),
                  ),
                  Container(
                    width: 8,
                    height: 16,
                    decoration: const BoxDecoration(
                      color: Color(0xFF9CA3AF),
                    ),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 500),
                      color: const Color(0xFF9CA3AF),
                    ),
                  ),
                ],
              );
            }
            
            final line = allLines[index];
            return Padding(
              padding: const EdgeInsets.only(bottom: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Line prefix
                  Text(
                    _getLinePrefix(line.type),
                    style: const TextStyle(
                      color: Color(0xFF6B7280),
                      fontSize: 14,
                      fontFamily: 'Courier',
                    ),
                  ),
                  // Line content
                  Expanded(
                    child: SelectableText(
                      line.content,
                      style: TextStyle(
                        color: _getLineColor(line.type),
                        fontSize: 14,
                        fontFamily: 'Courier',
                        height: 1.2,
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}
