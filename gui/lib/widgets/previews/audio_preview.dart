import 'dart:io';
import 'package:flutter/material.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:gui/data/models/file_attachment.dart';
import 'package:gui/core/config.dart';

/// Widget for previewing and playing audio files
class AudioPreview extends StatefulWidget {
  final FileAttachment attachment;
  final bool isCompact;
  final VoidCallback? onTap;
  final VoidCallback? onRemove;

  const AudioPreview({
    super.key,
    required this.attachment,
    this.isCompact = false,
    this.onTap,
    this.onRemove,
  });

  @override
  State<AudioPreview> createState() => _AudioPreviewState();
}

class _AudioPreviewState extends State<AudioPreview> {
  late AudioPlayer _audioPlayer;
  bool _isPlaying = false;
  bool _isLoading = false;
  Duration _duration = Duration.zero;
  Duration _position = Duration.zero;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    _audioPlayer = AudioPlayer();
    _setupAudioPlayer();
  }

  void _setupAudioPlayer() {
    _audioPlayer.onDurationChanged.listen((duration) {
      if (mounted) {
        setState(() {
          _duration = duration;
        });
      }
    });

    _audioPlayer.onPositionChanged.listen((position) {
      if (mounted) {
        setState(() {
          _position = position;
        });
      }
    });

    _audioPlayer.onPlayerStateChanged.listen((state) {
      if (mounted) {
        setState(() {
          _isPlaying = state == PlayerState.playing;
          _isLoading = state == PlayerState.playing && _position == Duration.zero;
        });
      }
    });

    _audioPlayer.onPlayerComplete.listen((event) {
      if (mounted) {
        setState(() {
          _isPlaying = false;
          _position = Duration.zero;
        });
      }
    });
  }

  Future<void> _togglePlayPause() async {
    try {
      setState(() {
        _errorMessage = null;
        _isLoading = true;
      });

      if (_isPlaying) {
        await _audioPlayer.pause();
      } else {
        String audioUrl = '';
        
        // Handle local files vs backend files separately
        if (widget.attachment.path != null && 
            (widget.attachment.path!.startsWith('/') || widget.attachment.path!.contains(':')) &&
            File(widget.attachment.path!).existsSync()) {
          // Local file - use file:// protocol
          audioUrl = 'file://${widget.attachment.path!.replaceAll('\\', '/')}';
          debugPrint('🎵 Playing local file: $audioUrl');
        } else {
          // Backend file - use API URL
          audioUrl = widget.attachment.getDisplayUrl(AppConfig.apiBaseUrl);
          debugPrint('🎵 Playing backend file: $audioUrl');
        }
        
        debugPrint('🎵 Attachment path: ${widget.attachment.path}');
        debugPrint('🎵 Final audio URL: $audioUrl');
        
        if (audioUrl.isEmpty) {
          throw Exception('Audio URL is empty');
        }
        
        if (_position == Duration.zero) {
          // First time playing or replaying from start
          await _audioPlayer.play(UrlSource(audioUrl));
        } else {
          // Resume from current position
          await _audioPlayer.resume();
        }
      }
    } catch (e) {
      debugPrint('❌ Audio playback error: $e');
      if (mounted) {
        setState(() {
          _errorMessage = 'Failed to play audio';
          _isPlaying = false;
          _isLoading = false;
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _seekTo(double value) async {
    final position = Duration(milliseconds: (value * _duration.inMilliseconds).round());
    await _audioPlayer.seek(position);
  }

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes;
    final seconds = duration.inSeconds % 60;
    return '${minutes.toString()}:${seconds.toString().padLeft(2, '0')}';
  }

  String _getDisplayName() {
    // Extract just the filename from full path
    if (widget.attachment.path != null) {
      return widget.attachment.path!.split(RegExp(r'[/\\]')).last;
    }
    return widget.attachment.filename;
  }

  @override
  void dispose() {
    _audioPlayer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: widget.onTap,
      child: Container(
        height: widget.isCompact ? 48 : 56,
        constraints: BoxConstraints(
          maxWidth: widget.isCompact ? 250 : 350,
        ),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12), // Pill shape
          border: Border.all(color: Colors.grey.shade300),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          child: Row(
            children: [
              // Play/Pause button
              GestureDetector(
                onTap: _togglePlayPause,
                child: Container(
                  width: widget.isCompact ? 36 : 44,
                  height: widget.isCompact ? 36 : 44,
                  decoration: BoxDecoration(
                    color: Colors.black,
                    shape: BoxShape.circle,
                  ),
                  child: Center(
                    child: _isLoading
                        ? SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : Icon(
                            _isPlaying ? Icons.pause : Icons.play_arrow,
                            color: Colors.white,
                            size: widget.isCompact ? 20 : 24,
                          ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              
              // Middle section - filename or progress bar
              Expanded(
                child: _isPlaying && _duration.inSeconds > 0
                    ? // Show progress bar when playing
                      SliderTheme(
                        data: SliderTheme.of(context).copyWith(
                          activeTrackColor: Colors.black,
                          inactiveTrackColor: Colors.grey.shade300,
                          thumbColor: Colors.black,
                          trackHeight: 4,
                          thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 8),
                          overlayShape: const RoundSliderOverlayShape(overlayRadius: 14),
                        ),
                        child: Slider(
                          value: _duration.inMilliseconds > 0
                              ? (_position.inMilliseconds / _duration.inMilliseconds).clamp(0.0, 1.0)
                              : 0.0,
                          onChanged: _duration.inMilliseconds > 0 ? _seekTo : null,
                        ),
                      )
                    : // Show filename when not playing
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          _getDisplayName(),
                          style: TextStyle(
                            fontSize: widget.isCompact ? 12 : 14,
                            fontWeight: FontWeight.w500,
                            color: Colors.grey.shade800,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
              ),
              
              const SizedBox(width: 12),
              
              // Timestamp (only show when playing)
              if (_isPlaying && _duration.inSeconds > 0) ...[
                Text(
                  '${_formatDuration(_position)} / ${_formatDuration(_duration)}',
                  style: TextStyle(
                    fontSize: widget.isCompact ? 11 : 12,
                    color: Colors.grey.shade700,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(width: 12),
              ],
              
              // Remove button (if provided)
              if (widget.onRemove != null)
                GestureDetector(
                  onTap: widget.onRemove,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: const BoxDecoration(
                      color: Colors.black,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      Icons.close,
                      color: Colors.white,
                      size: 16,
                    ),
                  ),
                ),
              
              // Error indicator
              if (_errorMessage != null)
                Padding(
                  padding: const EdgeInsets.only(left: 8),
                  child: Tooltip(
                    message: _errorMessage!,
                    child: Icon(
                      Icons.error_outline,
                      color: Colors.red.shade400,
                      size: 18,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}