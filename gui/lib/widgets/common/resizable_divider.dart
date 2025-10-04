import 'package:flutter/material.dart';

/// A resizable divider widget that allows users to resize adjacent panels
class ResizableDivider extends StatefulWidget {
  final bool isVertical;
  final double thickness;
  final Color? color;
  final Color? hoverColor;
  final Function(double delta)? onResize;
  final double minExtent;
  final double maxExtent;

  const ResizableDivider({
    Key? key,
    this.isVertical = false,
    this.thickness = 8.0,
    this.color,
    this.hoverColor,
    this.onResize,
    this.minExtent = 100.0,
    this.maxExtent = double.infinity,
  }) : super(key: key);

  @override
  State<ResizableDivider> createState() => _ResizableDividerState();
}

class _ResizableDividerState extends State<ResizableDivider> {
  bool _isHovering = false;
  bool _isDragging = false;
  double _startPosition = 0.0;

  @override
  Widget build(BuildContext context) {
    final Color effectiveColor = widget.color ?? Colors.grey.shade300;
    final Color effectiveHoverColor = widget.hoverColor ?? Colors.grey.shade400;
    
    return MouseRegion(
      cursor: widget.isVertical 
        ? SystemMouseCursors.resizeRow
        : SystemMouseCursors.resizeColumn,
      onEnter: (_) => setState(() => _isHovering = true),
      onExit: (_) => setState(() => _isHovering = false),
      child: GestureDetector(
        onPanStart: (details) {
          setState(() {
            _isDragging = true;
            _startPosition = widget.isVertical ? details.localPosition.dy : details.localPosition.dx;
          });
        },
        onPanUpdate: (details) {
          if (!_isDragging) return;
          
          final currentPosition = widget.isVertical ? details.localPosition.dy : details.localPosition.dx;
          final delta = currentPosition - _startPosition;
          
          widget.onResize?.call(delta);
          
          // KEY FIX: Update the start position for the next frame
          _startPosition = currentPosition;
        },
        onPanEnd: (_) {
          setState(() => _isDragging = false);
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: widget.isVertical ? double.infinity : widget.thickness,
          height: widget.isVertical ? widget.thickness : double.infinity,
          decoration: BoxDecoration(
            color: _isHovering || _isDragging 
              ? effectiveHoverColor 
              : effectiveColor,
            border: widget.isVertical
              ? Border.symmetric(
                  horizontal: BorderSide(
                    color: (_isHovering || _isDragging) 
                      ? Colors.blue.shade300 
                      : Colors.transparent,
                    width: 1.0,
                  ),
                )
              : Border.symmetric(
                  vertical: BorderSide(
                    color: (_isHovering || _isDragging) 
                      ? Colors.blue.shade300 
                      : Colors.transparent,
                    width: 1.0,
                  ),
                ),
          ),
          child: Center(
            child: Container(
              width: widget.isVertical ? 40 : 4,
              height: widget.isVertical ? 4 : 40,
              decoration: BoxDecoration(
                color: _isHovering || _isDragging 
                  ? Colors.blue.shade400 
                  : Colors.grey.shade500,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A widget that provides resizable panels with a divider
class ResizablePanels extends StatefulWidget {
  final Widget firstPanel;
  final Widget secondPanel;
  final bool isVertical;
  final double initialRatio;
  final double minFirstPanelRatio;
  final double maxFirstPanelRatio;
  final double dividerThickness;
  final Color? dividerColor;
  final Color? dividerHoverColor;

  const ResizablePanels({
    Key? key,
    required this.firstPanel,
    required this.secondPanel,
    this.isVertical = false,
    this.initialRatio = 0.5,
    this.minFirstPanelRatio = 0.2,
    this.maxFirstPanelRatio = 0.8,
    this.dividerThickness = 8.0,
    this.dividerColor,
    this.dividerHoverColor,
  }) : super(key: key);

  @override
  State<ResizablePanels> createState() => _ResizablePanelsState();
}

class _ResizablePanelsState extends State<ResizablePanels> {
  late double _ratio;

  @override
  void initState() {
    super.initState();
    _ratio = widget.initialRatio;
  }

  void _onResize(double delta, BoxConstraints constraints) {
    final totalSize = widget.isVertical ? constraints.maxHeight : constraints.maxWidth;
    final deltaRatio = delta / totalSize;
    
    setState(() {
      _ratio = (_ratio + deltaRatio).clamp(
        widget.minFirstPanelRatio,
        widget.maxFirstPanelRatio,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (widget.isVertical) {
          // Vertical layout (panels stacked top/bottom)
          final firstPanelHeight = (constraints.maxHeight - widget.dividerThickness) * _ratio;
          final secondPanelHeight = (constraints.maxHeight - widget.dividerThickness) * (1 - _ratio);
          
          return Column(
            children: [
              SizedBox(
                height: firstPanelHeight,
                child: widget.firstPanel,
              ),
              ResizableDivider(
                isVertical: true,
                thickness: widget.dividerThickness,
                color: widget.dividerColor,
                hoverColor: widget.dividerHoverColor,
                onResize: (delta) => _onResize(delta, constraints),
              ),
              SizedBox(
                height: secondPanelHeight,
                child: widget.secondPanel,
              ),
            ],
          );
        } else {
          // Horizontal layout (panels side by side)
          final firstPanelWidth = (constraints.maxWidth - widget.dividerThickness) * _ratio;
          final secondPanelWidth = (constraints.maxWidth - widget.dividerThickness) * (1 - _ratio);
          
          return Row(
            children: [
              SizedBox(
                width: firstPanelWidth,
                child: widget.firstPanel,
              ),
              ResizableDivider(
                isVertical: false,
                thickness: widget.dividerThickness,
                color: widget.dividerColor,
                hoverColor: widget.dividerHoverColor,
                onResize: (delta) => _onResize(delta, constraints),
              ),
              SizedBox(
                width: secondPanelWidth,
                child: widget.secondPanel,
              ),
            ],
          );
        }
      },
    );
  }
}