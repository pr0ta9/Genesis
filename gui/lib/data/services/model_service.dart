import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:gui/core/config.dart';
import 'package:gui/data/models/ai_model.dart';

/// Service for fetching and selecting AI models
class ModelService {
  const ModelService();

  /// Fetch available models from the backend
  Future<List<AIModel>> fetchModels() async {
    debugPrint('🌐 API CALL: GET /models/');
    final url = AppConfig.api('/models/');
    debugPrint('🔗 FULL URL: $url');

    try {
      final res = await http.get(url, headers: _jsonHeaders);
      debugPrint('📡 FETCH MODELS RESPONSE STATUS: ${res.statusCode}');
      
      if (res.statusCode >= 200 && res.statusCode < 300) {
        final decoded = jsonDecode(res.body) as Map<String, dynamic>;
        final modelsList = decoded['models'] as List<dynamic>?;
        
        if (modelsList == null) {
          debugPrint('❌ No models list in response');
          return [];
        }

        final models = modelsList
            .map((m) => AIModel.fromJson(m as Map<String, dynamic>))
            .toList();
        
        debugPrint('✅ Fetched ${models.length} models');
        return models;
      } else {
        debugPrint('❌ Failed to fetch models: ${res.statusCode}');
        throw HttpException('Failed to fetch models: ${res.statusCode}', body: res.body);
      }
    } catch (e) {
      debugPrint('❌ Error fetching models: $e');
      rethrow;
    }
  }

  /// Get current selected model from the backend
  Future<String?> getCurrentModel() async {
    debugPrint('🌐 API CALL: GET /models/ (for current model)');
    final url = AppConfig.api('/models/');

    try {
      final res = await http.get(url, headers: _jsonHeaders);
      
      if (res.statusCode >= 200 && res.statusCode < 300) {
        final decoded = jsonDecode(res.body) as Map<String, dynamic>;
        final current = decoded['current'] as String?;
        debugPrint('✅ Current model: $current');
        return current;
      } else {
        debugPrint('❌ Failed to get current model: ${res.statusCode}');
        return null;
      }
    } catch (e) {
      debugPrint('❌ Error getting current model: $e');
      return null;
    }
  }

  /// Select a model on the backend
  Future<void> selectModel(
    String modelId, {
    String? awsRegion,
    String? awsAccessKeyId,
    String? awsSecretAccessKey,
  }) async {
    debugPrint('🌐 API CALL: POST /models/select with modelId: $modelId');
    
    try {
      // Parse the model ID (format: "provider:model")
      final parts = modelId.split(':');
      final provider = parts.isNotEmpty ? parts[0] : 'ollama';
      final model = parts.length > 1 ? parts.sublist(1).join(':') : modelId;

      final url = AppConfig.api('/models/select');
      debugPrint('🔗 FULL URL: $url');

      // Build request body
      final body = {
        'provider': provider,
        'model': model,
      };

      // Add AWS credentials if provided (for Bedrock)
      if (awsRegion != null) body['aws_region'] = awsRegion;
      if (awsAccessKeyId != null) body['aws_access_key_id'] = awsAccessKeyId;
      if (awsSecretAccessKey != null) body['aws_secret_access_key'] = awsSecretAccessKey;

      debugPrint('📦 REQUEST BODY: ${jsonEncode(body)}');

      final res = await http.post(
        url,
        headers: _jsonHeaders,
        body: jsonEncode(body),
      );
      debugPrint('📡 SELECT MODEL RESPONSE STATUS: ${res.statusCode}');
      debugPrint('📡 SELECT MODEL RESPONSE BODY: ${res.body}');

      if (res.statusCode < 200 || res.statusCode >= 300) {
        throw HttpException('Failed to select model: ${res.statusCode}', body: res.body);
      }

      debugPrint('✅ Model selected successfully');
    } catch (e) {
      debugPrint('❌ Error selecting model: $e');
      rethrow;
    }
  }

  Map<String, String> get _jsonHeaders => const {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      };
}

class HttpException implements Exception {
  final String message;
  final String? body;
  const HttpException(this.message, {this.body});
  
  @override
  String toString() => 'HttpException: $message${body != null ? '\n$body' : ''}';
}

