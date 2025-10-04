import 'package:flutter/material.dart';
import 'package:gui/data/services/streaming_service.dart';

/// Widget that displays a single reasoning section for a message
class ReasoningSectionWidget extends StatefulWidget {
  final WorkflowSection section;

  const ReasoningSectionWidget({
    super.key,
    required this.section,
  });

  @override
  State<ReasoningSectionWidget> createState() => _ReasoningSectionWidgetState();
}

class _ReasoningSectionWidgetState extends State<ReasoningSectionWidget> {
  bool _isManuallyExpanded = false;

  @override
  void initState() {
    super.initState();
    // Initialize manual expansion state
    _isManuallyExpanded = widget.section.isAutoExpanded;
  }

  @override
  void didUpdateWidget(ReasoningSectionWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Update expansion state when auto-expansion changes
    if (oldWidget.section.isAutoExpanded != widget.section.isAutoExpanded) {
      setState(() {
        _isManuallyExpanded = widget.section.isAutoExpanded;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasReasoning = widget.section.reasoningContent.trim().isNotEmpty;
    final thinkingTime = widget.section.thinkingTime ?? 0.0;
    final timeText = (thinkingTime * 10).round() / 10; // Round to 1 decimal
    
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Title line (bold, matching Next.js fontSize 15)
          SelectableText(
            widget.section.title,
            style: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.bold,
              color: Colors.black87,
            ),
          ),
          
          // Thought toggle line (collapsible)
          if (hasReasoning) ...[
            Padding(
              padding: const EdgeInsets.only(left: 8, top: 2),
              child: GestureDetector(
                onTap: () {
                  setState(() {
                    _isManuallyExpanded = !_isManuallyExpanded;
                  });
                },
                child: MouseRegion(
                  cursor: SystemMouseCursors.click,
                  child: Text(
                    widget.section.isThinking 
                        ? 'Thinking...' 
                        : 'Thought for ${timeText.toStringAsFixed(1)}s',
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.grey.shade700,
                    ),
                  ),
                ),
              ),
            ),
            
            // Expanded reasoning content
            if (_isManuallyExpanded) ...[
              Container(
                margin: const EdgeInsets.only(left: 8, top: 4),
                padding: const EdgeInsets.only(left: 12, top: 8, right: 8, bottom: 8),
                decoration: BoxDecoration(
                  border: Border(
                    left: BorderSide(
                      color: Colors.grey.shade300,
                      width: 2,
                    ),
                  ),
                ),
                child: SelectableText(
                  widget.section.reasoningContent,
                  style: const TextStyle(
                    fontSize: 12,
                    height: 1.4,
                    color: Colors.black87,
                    fontFamily: 'monospace',
                  ),
                ),
              ),
            ],
          ],
          
          // Clarification if present
          if (widget.section.clarification != null && widget.section.clarification!.isNotEmpty) ...[
            Padding(
              padding: const EdgeInsets.only(left: 8, top: 4),
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  border: Border.all(color: Colors.blue.shade200),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: SelectableText(
                  'Clarification: ${widget.section.clarification!}',
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.blue.shade800,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Widget that displays all reasoning sections for a message
class MessageReasoningDisplay extends StatelessWidget {
  final WorkflowState? workflow;
  final Widget? progressBar; // Optional progress bar to render after execute section

  const MessageReasoningDisplay({
    super.key,
    required this.workflow,
    this.progressBar,
  });

  @override
  Widget build(BuildContext context) {
    if (workflow == null || workflow!.sections.isEmpty) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.only(top: 8, bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Display sections in order, with progress bar after execute section
          for (final nodeKey in workflow!.sectionOrder) ...[
            if (workflow!.sections[nodeKey] != null)
              ReasoningSectionWidget(
                section: workflow!.sections[nodeKey]!,
              ),
            // Insert progress bar after execute section (before finalize)
            if (nodeKey == 'execute' && progressBar != null)
              Padding(
                padding: const EdgeInsets.only(top: 4, bottom: 12),
                child: progressBar!,
              ),
          ],
        ],
      ),
    );
  }
}
