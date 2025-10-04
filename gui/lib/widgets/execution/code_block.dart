import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:gui/core/config.dart';
import 'package:gui/data/services/streaming_service.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:async';

/// Widget that displays tool source code with syntax highlighting
class CodeBlock extends StatefulWidget {
  final StreamingService? streamingService;
  final String? currentToolName;
  final int? currentStepIndex;
  final List<String>? chosenPath;
  final String? executionOutputPath;

  const CodeBlock({
    Key? key,
    this.streamingService,
    this.currentToolName,
    this.currentStepIndex,
    this.chosenPath,
    this.executionOutputPath,
  }) : super(key: key);

  @override
  State<CodeBlock> createState() => _CodeBlockState();
}

class _CodeBlockState extends State<CodeBlock> {
  String _source = '';
  String _fileName = '';
  bool _isLoading = false;
  String? _error;
  
  // Scroll controller for the code content
  final ScrollController _scrollController = ScrollController();
  
  // Stream subscription for live updates
  StreamSubscription<String>? _toolSubscription;
  String? _streamingToolName;

  @override
  void initState() {
    super.initState();
    _setupStreamingListeners();
    _loadToolSource();
  }

  @override
  void didUpdateWidget(CodeBlock oldWidget) {
    super.didUpdateWidget(oldWidget);
    
    // Reload source if the tool changes
    if (widget.currentToolName != oldWidget.currentToolName ||
        widget.currentStepIndex != oldWidget.currentStepIndex ||
        widget.chosenPath != oldWidget.chosenPath ||
        widget.streamingService != oldWidget.streamingService) {
      _setupStreamingListeners();
      _loadToolSource();
    }
  }

  @override
  void dispose() {
    _toolSubscription?.cancel();
    _scrollController.dispose();
    super.dispose();
  }
  
  /// Setup streaming listeners for live tool updates
  void _setupStreamingListeners() {
    _toolSubscription?.cancel();
    
    if (widget.streamingService != null) {
      _toolSubscription = widget.streamingService!.currentTool.listen((toolName) {
        setState(() {
          _streamingToolName = toolName;
        });
        _loadToolSource();
      });
    }
  }

  /// Load tool source code from the API
  Future<void> _loadToolSource() async {
    try {
      // Determine which tool to load
      String? toolName = _determineToolName();
      
      if (toolName == null) {
        setState(() {
          _source = '';
          _fileName = 'tool.py';
          _isLoading = false;
          _error = null;
        });
        return;
      }

      setState(() {
        _isLoading = true;
        _error = null;
        _fileName = '$toolName.py';
      });

      // Fetch source code from the API
      final url = AppConfig.api('/artifacts/tools/source/$toolName');
      final response = await http.get(url);

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final source = data['source'] ?? '';
        
        setState(() {
          _source = source;
          _isLoading = false;
        });
      } else {
        setState(() {
          _source = '';
          _isLoading = false;
          _error = 'Failed to load source code';
        });
      }
    } catch (e) {
      setState(() {
        _source = '';
        _isLoading = false;
        _error = 'Error loading source: $e';
      });
    }
  }

  /// Determine which tool name to use for loading source
  String? _determineToolName() {
    // Priority: streaming tool (live execution), explicit selected tool, otherwise selected step in chosenPath, 
    // otherwise fallback to first chosen step from backend state
    
    String? toolName = _streamingToolName ?? widget.currentToolName;
    
    if (toolName == null && 
        widget.currentStepIndex != null && 
        widget.chosenPath != null && 
        widget.currentStepIndex! >= 0 && 
        widget.currentStepIndex! < widget.chosenPath!.length) {
      final nodeId = widget.chosenPath![widget.currentStepIndex!];
      if (!_isEndpointNode(nodeId)) {
        toolName = nodeId;
      }
    }
    
    if (toolName == null && widget.chosenPath != null) {
      final chosen = widget.chosenPath!;
      if (chosen.isNotEmpty) {
        final firstTool = chosen[0];
        
        if (!_isEndpointNode(firstTool)) {
          toolName = firstTool;
        }
      }
    }
    
    return toolName;
  }

  /// Check if a node is an endpoint node
  bool _isEndpointNode(String nodeId) {
    return nodeId.endsWith('_IN') || nodeId.endsWith('_OUT');
  }

  /// Copy source code to clipboard
  void _copyToClipboard() {
    if (_source.isNotEmpty) {
      Clipboard.setData(ClipboardData(text: _source));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Source code copied to clipboard'),
          duration: Duration(seconds: 2),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF111827), // Dark background
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

  /// Build the header with file name and controls
  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: const BoxDecoration(
        color: Color(0xFF1F2937), // Darker header
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(12),
          topRight: Radius.circular(12),
        ),
        border: Border(
          bottom: BorderSide(color: Color(0xFF374151)),
        ),
      ),
      child: Row(
        children: [
          // File icon
          const Icon(
            Icons.code,
            color: Color(0xFF9CA3AF),
            size: 16,
          ),
          const SizedBox(width: 8),
          // File name
          Text(
            _fileName,
            style: const TextStyle(
              color: Color(0xFFD1D5DB),
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
          const Spacer(),
          // Copy button
          if (_source.isNotEmpty)
            IconButton(
              onPressed: _copyToClipboard,
              icon: const Icon(
                Icons.copy,
                color: Color(0xFF9CA3AF),
                size: 16,
              ),
              tooltip: 'Copy to clipboard',
              padding: const EdgeInsets.all(4),
              constraints: const BoxConstraints(
                minWidth: 24,
                minHeight: 24,
              ),
            ),
        ],
      ),
    );
  }

  /// Build the main content area
  Widget _buildContent() {
    if (_isLoading) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(
              color: Color(0xFF6B7280),
            ),
            SizedBox(height: 16),
            Text(
              'Loading source code...',
              style: TextStyle(
                color: Color(0xFF9CA3AF),
                fontSize: 14,
              ),
            ),
          ],
        ),
      );
    }

    if (_error != null) {
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
              _error!,
              style: const TextStyle(
                color: Color(0xFFEF4444),
                fontSize: 14,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadToolSource,
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF374151),
                foregroundColor: const Color(0xFFD1D5DB),
              ),
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    if (_source.isEmpty) {
      return const Center(
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
              'No source code available',
              style: TextStyle(
                color: Color(0xFF9CA3AF),
                fontSize: 14,
              ),
            ),
            SizedBox(height: 4),
            Text(
              'Select a tool step to view its code',
              style: TextStyle(
                color: Color(0xFF6B7280),
                fontSize: 12,
              ),
            ),
          ],
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(16),
      child: Scrollbar(
        controller: _scrollController,
        child: SingleChildScrollView(
          controller: _scrollController,
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SelectableText(
              _source,
              style: const TextStyle(
                color: Color(0xFFD1D5DB),
                fontSize: 13,
                fontFamily: 'Courier', // Monospace font
                height: 1.5,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Syntax highlighted code block widget (future enhancement)
class SyntaxHighlightedCodeBlock extends StatelessWidget {
  final String source;
  final String language;

  const SyntaxHighlightedCodeBlock({
    Key? key,
    required this.source,
    this.language = 'python',
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    // TODO: Implement syntax highlighting using a package like highlight.dart
    // For now, return simple text
    return SelectableText(
      source,
      style: const TextStyle(
        color: Color(0xFFD1D5DB),
        fontSize: 13,
        fontFamily: 'Courier',
        height: 1.5,
      ),
    );
  }
}
