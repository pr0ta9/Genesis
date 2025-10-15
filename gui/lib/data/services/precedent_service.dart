import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:gui/core/config.dart';

/// Service for managing precedents
class PrecedentService {
  const PrecedentService();

  /// Fetch all precedents
  Future<List<Map<String, dynamic>>> fetchPrecedents() async {
    debugPrint('🌐 API CALL: GET /precedent/');
    final url = AppConfig.api('/precedent/');
    debugPrint('🔗 FULL URL: $url');

    try {
      final res = await http.get(url, headers: _jsonHeaders);
      debugPrint('📡 FETCH PRECEDENTS RESPONSE STATUS: ${res.statusCode}');
      
      if (res.statusCode >= 200 && res.statusCode < 300) {
        final decoded = jsonDecode(res.body) as Map<String, dynamic>;
        final precedentsList = decoded['precedents'] as List<dynamic>?;
        
        if (precedentsList == null) {
          debugPrint('❌ No precedents list in response');
          return [];
        }

        final precedents = precedentsList
            .map((p) => p as Map<String, dynamic>)
            .toList();
        
        debugPrint('✅ Fetched ${precedents.length} precedents');
        return precedents;
      } else {
        debugPrint('❌ Failed to fetch precedents: ${res.statusCode}');
        throw HttpException('Failed to fetch precedents: ${res.statusCode}', body: res.body);
      }
    } catch (e) {
      debugPrint('❌ Error fetching precedents: $e');
      rethrow;
    }
  }

  /// Delete specific precedents by UUID list
  Future<Map<String, dynamic>> deletePrecedents(List<String> uuids) async {
    debugPrint('🌐 API CALL: DELETE /precedent/ with ${uuids.length} UUIDs');
    final url = AppConfig.api('/precedent/');
    debugPrint('🔗 FULL URL: $url');

    try {
      final res = await http.delete(
        url,
        headers: _jsonHeaders,
        body: jsonEncode({'uuids': uuids}),
      );
      debugPrint('📡 DELETE PRECEDENTS RESPONSE STATUS: ${res.statusCode}');
      debugPrint('📡 DELETE PRECEDENTS RESPONSE BODY: ${res.body}');

      if (res.statusCode >= 200 && res.statusCode < 300) {
        final result = jsonDecode(res.body) as Map<String, dynamic>;
        debugPrint('✅ Deleted ${result['deleted_count']} precedents');
        return result;
      } else {
        throw HttpException('Failed to delete precedents: ${res.statusCode}', body: res.body);
      }
    } catch (e) {
      debugPrint('❌ Error deleting precedents: $e');
      rethrow;
    }
  }

  /// Delete all precedents
  Future<Map<String, dynamic>> deleteAllPrecedents() async {
    debugPrint('🌐 API CALL: DELETE /precedent/all');
    final url = AppConfig.api('/precedent/all');
    debugPrint('🔗 FULL URL: $url');

    try {
      final res = await http.delete(url, headers: _jsonHeaders);
      debugPrint('📡 DELETE ALL PRECEDENTS RESPONSE STATUS: ${res.statusCode}');
      debugPrint('📡 DELETE ALL PRECEDENTS RESPONSE BODY: ${res.body}');

      if (res.statusCode >= 200 && res.statusCode < 300) {
        final result = jsonDecode(res.body) as Map<String, dynamic>;
        debugPrint('✅ Deleted all precedents');
        return result;
      } else {
        throw HttpException('Failed to delete all precedents: ${res.statusCode}', body: res.body);
      }
    } catch (e) {
      debugPrint('❌ Error deleting all precedents: $e');
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

