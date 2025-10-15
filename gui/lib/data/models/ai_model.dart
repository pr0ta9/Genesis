/// Data model for an AI model returned from the /models API
class AIModel {
  final String id;
  final String provider;
  final String name;

  const AIModel({
    required this.id,
    required this.provider,
    required this.name,
  });

  factory AIModel.fromJson(Map<String, dynamic> json) {
    return AIModel(
      id: json['id'] as String,
      provider: json['provider'] as String,
      name: json['name'] as String,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'provider': provider,
      'name': name,
    };
  }

  /// Display name for dropdown (e.g., "gpt-oss:20b (ollama)")
  String get displayName => '$name ($provider)';

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is AIModel && other.id == id;
  }

  @override
  int get hashCode => id.hashCode;

  @override
  String toString() => 'AIModel(id: $id, provider: $provider, name: $name)';
}

