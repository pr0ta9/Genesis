class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  static Uri api(String path, [Map<String, dynamic>? query]) {
    final base = Uri.parse(apiBaseUrl);
    final joinedPath = (
      (base.path.isEmpty || base.path == '/') ? '' : base.path
    ) + (path.startsWith('/') ? path : '/$path');
    return Uri(
      scheme: base.scheme,
      host: base.host,
      port: base.port,
      path: joinedPath.replaceAll('//', '/'),
      queryParameters: query?.map((k, v) => MapEntry(k, '$v')),
    );
  }

  // Build a URI against the server root (ignores any path prefix in API_BASE_URL)
  static Uri root(String path, [Map<String, dynamic>? query]) {
    final base = Uri.parse(apiBaseUrl);
    return Uri(
      scheme: base.scheme,
      host: base.host,
      port: base.port,
      path: path.startsWith('/') ? path : '/$path',
      queryParameters: query?.map((k, v) => MapEntry(k, '$v')),
    );
  }
}


