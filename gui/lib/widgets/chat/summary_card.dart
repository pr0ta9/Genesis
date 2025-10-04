import 'package:flutter/material.dart';

/// A card that summarizes execution results and allows triggering execution panel
class SummaryCard extends StatefulWidget {
  final List<List<String>>? allPaths;
  final List<String>? chosenPath;
  final VoidCallback? onTap;

  const SummaryCard({
    Key? key,
    this.allPaths,
    this.chosenPath,
    this.onTap,
  }) : super(key: key);

  @override
  State<SummaryCard> createState() => _SummaryCardState();
}

class _SummaryCardState extends State<SummaryCard> 
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _shimmerAnimation;
  bool _isHovering = false;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _shimmerAnimation = Tween<double>(
      begin: -1.0,
      end: 2.0,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    ));
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hasData = (widget.allPaths?.isNotEmpty ?? false) || 
                   (widget.chosenPath?.isNotEmpty ?? false);
    
    if (!hasData) {
      return const SizedBox.shrink();
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 12),
      child: MouseRegion(
        onEnter: (_) {
          setState(() => _isHovering = true);
          _animationController.forward();
        },
        onExit: (_) {
          setState(() => _isHovering = false);
          _animationController.reset();
        },
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: widget.onTap,
            borderRadius: BorderRadius.circular(12),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: _isHovering ? Colors.grey.shade50 : Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: _isHovering ? Colors.grey.shade300 : Colors.grey.shade200,
                  width: 1,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(_isHovering ? 0.08 : 0.04),
                    blurRadius: _isHovering ? 8 : 4,
                    spreadRadius: 0,
                    offset: Offset(0, _isHovering ? 4 : 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Header row
                  Row(
                    children: [
                      // Execution icon with left-to-right fill animation
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: _isHovering ? Colors.grey.shade50 : Colors.white,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: AnimatedBuilder(
                          animation: _shimmerAnimation,
                          builder: (context, child) {
                            return ShaderMask(
                              shaderCallback: (Rect bounds) {
                                if (!_isHovering) {
                                  // No animation when not hovering
                                  return LinearGradient(
                                    colors: [Colors.grey.shade600, Colors.grey.shade600],
                                  ).createShader(bounds);
                                }
                                
                                // Left-to-right fill animation
                                final progress = (_shimmerAnimation.value + 1) / 3; // Normalize to 0-1
                                return LinearGradient(
                                  begin: Alignment.centerLeft,
                                  end: Alignment.centerRight,
                                  colors: [
                                    Colors.blue.shade600,
                                    Colors.blue.shade600,
                                    Colors.grey.shade600,
                                    Colors.grey.shade600,
                                  ],
                                  stops: [
                                    0.0,
                                    progress.clamp(0.0, 1.0),
                                    progress.clamp(0.0, 1.0),
                                    1.0,
                                  ],
                                ).createShader(bounds);
                              },
                              child: Icon(
                                Icons.account_tree,
                                size: 18,
                                color: Colors.white, // Base color for ShaderMask
                              ),
                            );
                          },
                        ),
                      ),
                      const SizedBox(width: 12),
                      
                      // Title and subtitle
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Execution Workflow',
                              style: TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                                color: Colors.grey.shade800,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              _getSubtitleText(),
                              style: TextStyle(
                                fontSize: 12,
                                color: Colors.grey.shade600,
                              ),
                            ),
                          ],
                        ),
                      ),
                      
                      // Animated arrow on hover
                      AnimatedOpacity(
                        duration: const Duration(milliseconds: 200),
                        opacity: _isHovering ? 1.0 : 0.0,
                        child: Icon(
                          Icons.arrow_forward,
                          size: 16,
                          color: Colors.blue.shade600,
                        ),
                      ),
                    ],
                  ),
                  
                  const SizedBox(height: 12),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  String _getSubtitleText() {
    final pathCount = widget.allPaths?.length ?? 0;
    final hasChosenPath = widget.chosenPath?.isNotEmpty ?? false;
    
    if (pathCount > 0 && hasChosenPath) {
      return '$pathCount paths explored • Path selected';
    } else if (pathCount > 0) {
      return '$pathCount paths explored';
    } else if (hasChosenPath) {
      return 'Path selected';
    } else {
      return 'Click to view execution details';
    }
  }
}
