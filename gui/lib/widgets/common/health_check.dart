import 'dart:async';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:gui/core/config.dart';

class HealthCheck extends StatefulWidget {
  const HealthCheck({super.key});

  @override
  State<HealthCheck> createState() => _HealthCheckState();
}

class _HealthCheckState extends State<HealthCheck> {
  String? _error; // null means OK (hide), string means show error banner
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _check();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) => _check());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _check() async {
    try {
      // Check dedicated health endpoint at server root
      final uri = AppConfig.root('/health');
      final res = await http.get(uri).timeout(const Duration(seconds: 5));
      if (res.statusCode >= 200 && res.statusCode < 300) {
        if (_error != null) {
          setState(() => _error = null);
        }
      } else {
        setState(() => _error = 'Backend returned ${res.statusCode}: ${res.reasonPhrase ?? 'Unknown'}');
      }
    } catch (e) {
      setState(() => _error = 'Failed to connect to backend: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    // Hide entirely when healthy
    if (_error == null) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.red.shade50,
        border: Border.all(color: Colors.red.shade200),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(
            Icons.error_outline,
            size: 20,
            color: Colors.red.shade600,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: SelectableText(
              _error ?? '',
              style: TextStyle(
                fontSize: 12,
                color: Colors.red.shade700,
              ),
            ),
          ),
          TextButton(
            onPressed: _check,
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}


