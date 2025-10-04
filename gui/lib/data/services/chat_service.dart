import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:gui/core/config.dart';

class ChatService {
  const ChatService();

  Future<Map<String, dynamic>> createChat() async {
    debugPrint('🌐 API CALL: POST /chats/');
    final url = AppConfig.api('/chats/');
    debugPrint('🔗 FULL URL: $url');
    
    final res = await http.post(url, headers: _jsonHeaders);
    debugPrint('📡 CREATE CHAT RESPONSE STATUS: ${res.statusCode}');
    debugPrint('📡 CREATE CHAT RESPONSE BODY: ${res.body}');
    
    _ensureOk(res);
    final decoded = _decode(res);
    
    debugPrint('🎯 DECODED CREATE CHAT RESPONSE: $decoded');
    
    return decoded;
  }

  Future<List<Map<String, dynamic>>> listChats() async {
    final url = AppConfig.api('/chats/');
    final res = await http.get(url, headers: _jsonHeaders);
    _ensureOk(res);
    final data = jsonDecode(res.body);
    if (data is List) {
      return data.cast<Map>().map((e) => e.cast<String, dynamic>()).toList();
    }
    throw const FormatException('Unexpected response for listChats');
  }

  Future<Map<String, dynamic>> getChatDetail(String chatId) async {
    debugPrint('🌐 API CALL: GET /chats/$chatId');
    final url = AppConfig.api('/chats/$chatId');
    debugPrint('🔗 FULL URL: $url');
    
    final res = await http.get(url, headers: _jsonHeaders);
    debugPrint('📡 API RESPONSE STATUS: ${res.statusCode}');
    debugPrint('📡 API RESPONSE BODY LENGTH: ${res.body.length} chars');
    
    _ensureOk(res);
    final decoded = _decode(res);
    
    debugPrint('🎯 DECODED RESPONSE KEYS: ${decoded.keys.toList()}');
    
    if (decoded.containsKey('messages')) {
      final messages = decoded['messages'] as List?;
      debugPrint('💬 MESSAGES IN RESPONSE: ${messages?.length ?? 0}');
      
      // Show structure of first message
      if (messages != null && messages.isNotEmpty) {
        debugPrint('📄 FIRST MESSAGE STRUCTURE: ${messages.first}');
        
        // Count by role
        var userCount = 0;
        var assistantCount = 0;
        for (var msg in messages) {
          if (msg is Map && msg.containsKey('role')) {
            if (msg['role'] == 'user') userCount++;
            if (msg['role'] == 'assistant') assistantCount++;
          }
        }
        debugPrint('👤 USER MESSAGES: $userCount, 🤖 ASSISTANT MESSAGES: $assistantCount');
      }
    }
    
    return decoded;
  }

  /// Get state data for a message by message ID
  Future<Map<String, dynamic>?> getMessageState(int messageId) async {
    try {
      debugPrint('🌐 API CALL: GET /messages/$messageId');
      final url = AppConfig.api('/messages/$messageId');
      debugPrint('🔗 FULL URL: $url');
      
      final res = await http.get(url, headers: _jsonHeaders);
      debugPrint('📡 MESSAGE STATE RESPONSE STATUS: ${res.statusCode}');
      
      if (res.statusCode == 200) {
        final decoded = _decode(res);
        debugPrint('🎯 MESSAGE STATE DATA KEYS: ${decoded.keys.toList()}');
        
        // Log specific path data if available
        if (decoded.containsKey('node')) {
          debugPrint('🎯 NODE: ${decoded['node']}');
        }
        if (decoded.containsKey('all_paths')) {
          final allPaths = decoded['all_paths'];
          debugPrint('📋 ALL_PATHS FOUND: ${allPaths is List ? allPaths.length : 'not a list'} - Type: ${allPaths.runtimeType}');
        } else {
          debugPrint('❌ NO ALL_PATHS field in response');
        }
        
        if (decoded.containsKey('chosen_path')) {
          final chosenPath = decoded['chosen_path'];
          debugPrint('🎯 CHOSEN_PATH FOUND: ${chosenPath is List ? chosenPath.length : 'not a list'} - Type: ${chosenPath.runtimeType}');
          if (chosenPath is List) {
            debugPrint('🎯 CHOSEN_PATH CONTENT: $chosenPath');
          }
        } else {
          debugPrint('❌ NO CHOSEN_PATH field in response');
        }
        
        return decoded;
      } else {
        debugPrint('❌ Failed to fetch message state: ${res.statusCode}');
        return null;
      }
    } catch (e) {
      debugPrint('❌ Error fetching message state: $e');
      return null;
    }
  }

  Future<Map<String, dynamic>> updateChat(String chatId, {required String title}) async {
    debugPrint('🌐 API CALL: PUT /chats/$chatId with title: $title');
    final url = AppConfig.api('/chats/$chatId');
    debugPrint('🔗 FULL URL: $url');
    
    final body = jsonEncode({'title': title});
    debugPrint('📤 REQUEST BODY: $body');
    
    final res = await http.put(url, headers: _jsonHeaders, body: body);
    debugPrint('📡 UPDATE CHAT RESPONSE STATUS: ${res.statusCode}');
    debugPrint('📡 UPDATE CHAT RESPONSE BODY: ${res.body}');
    
    _ensureOk(res);
    final decoded = _decode(res);
    
    debugPrint('🎯 DECODED UPDATE CHAT RESPONSE: $decoded');
    
    return decoded;
  }

  Future<Map<String, dynamic>> deleteChat(String chatId) async {
    debugPrint('🌐 API CALL: DELETE /chats/$chatId');
    final url = AppConfig.api('/chats/$chatId');
    debugPrint('🔗 FULL URL: $url');
    
    final res = await http.delete(url, headers: _jsonHeaders);
    debugPrint('📡 DELETE CHAT RESPONSE STATUS: ${res.statusCode}');
    debugPrint('📡 DELETE CHAT RESPONSE BODY: ${res.body}');
    
    _ensureOk(res);
    final decoded = _decode(res);
    
    debugPrint('🎯 DECODED DELETE CHAT RESPONSE: $decoded');
    
    return decoded;
  }

  Future<Map<String, dynamic>> savePrecedent(int messageId) async {
    debugPrint('🌐 API CALL: POST /messages/$messageId/precedent');
    final url = AppConfig.api('/messages/$messageId/precedent');
    debugPrint('🔗 FULL URL: $url');
    
    final res = await http.post(url, headers: _jsonHeaders);
    debugPrint('📡 SAVE PRECEDENT RESPONSE STATUS: ${res.statusCode}');
    debugPrint('📡 SAVE PRECEDENT RESPONSE BODY: ${res.body}');
    
    _ensureOk(res);
    final decoded = _decode(res);
    
    debugPrint('🎯 DECODED SAVE PRECEDENT RESPONSE: $decoded');
    
    return decoded;
  }

  Future<Map<String, dynamic>> deletePrecedent(int messageId) async {
    debugPrint('🌐 API CALL: DELETE /messages/$messageId/precedent');
    final url = AppConfig.api('/messages/$messageId/precedent');
    debugPrint('🔗 FULL URL: $url');
    
    final res = await http.delete(url, headers: _jsonHeaders);
    debugPrint('📡 DELETE PRECEDENT RESPONSE STATUS: ${res.statusCode}');
    debugPrint('📡 DELETE PRECEDENT RESPONSE BODY: ${res.body}');
    
    _ensureOk(res);
    final decoded = _decode(res);
    
    debugPrint('🎯 DECODED DELETE PRECEDENT RESPONSE: $decoded');
    
    return decoded;
  }

  Future<Map<String, dynamic>> sendMessage(String chatId, String message) async {
    // This method is now deprecated in favor of using StreamingService
    // Kept for backward compatibility
    final url = AppConfig.api('/messages/$chatId');
    // Use form data instead of JSON since the API expects form parameters
    final res = await http.post(
      url,
      headers: {'Accept': 'application/json'},
      body: {'message': message},
    );
    _ensureOk(res);
    return _decode(res);
  }

  Map<String, String> get _jsonHeaders => const {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      };

  void _ensureOk(http.Response res) {
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw HttpException('HTTP ${res.statusCode}: ${res.reasonPhrase}', body: res.body);
    }
  }

  Map<String, dynamic> _decode(http.Response res) {
    final body = res.body;
    if (body.isEmpty) return <String, dynamic>{};
    final decoded = jsonDecode(body);
    if (decoded is Map) return decoded.cast<String, dynamic>();
    throw const FormatException('Expected JSON object');
  }
}

class HttpException implements Exception {
  final String message;
  final String? body;
  const HttpException(this.message, {this.body});
  @override
  String toString() => 'HttpException: $message${body != null ? '\n$body' : ''}';
}


