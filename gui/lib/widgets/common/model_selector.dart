import 'package:flutter/material.dart';
import 'package:gui/data/models/ai_model.dart';
import 'package:gui/data/services/model_service.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';

/// A dropdown widget for selecting AI models
class ModelSelector extends StatefulWidget {
  final Function(AIModel)? onModelChanged;
  final bool showLabel;

  const ModelSelector({
    super.key,
    this.onModelChanged,
    this.showLabel = true,
  });

  @override
  State<ModelSelector> createState() => ModelSelectorState();
}

class ModelSelectorState extends State<ModelSelector> {
  final ModelService _service = const ModelService();
  List<AIModel> _models = [];
  AIModel? _selectedModel;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadModels();
  }

  Future<void> _loadModels() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      // Fetch models from backend
      final backendModels = await _service.fetchModels();
      
      // Load Bedrock models from settings
      final bedrockModels = await _loadBedrockModelsFromSettings();
      
      // Combine backend models with Bedrock models
      final allModels = [...backendModels, ...bedrockModels];
      
      // Load last selected model from local storage
      final prefs = await SharedPreferences.getInstance();
      final savedModelId = prefs.getString('last_selected_model');
      
      // Try to find saved model, fall back to backend current model, then first available
      AIModel? modelToSelect;
      
      if (savedModelId != null) {
        debugPrint('📂 Found saved model: $savedModelId');
        modelToSelect = allModels.firstWhere(
          (m) => m.id == savedModelId,
          orElse: () => AIModel(id: '', provider: '', name: ''),
        );
        if (modelToSelect.id.isEmpty) {
          debugPrint('⚠️ Saved model not found in available models');
          modelToSelect = null;
        }
      }
      
      // Fall back to backend's current model if no saved model
      if (modelToSelect == null) {
        final currentModelId = await _service.getCurrentModel();
        if (currentModelId != null) {
          modelToSelect = allModels.firstWhere(
            (m) => m.id == currentModelId,
            orElse: () => AIModel(id: '', provider: '', name: ''),
          );
          if (modelToSelect.id.isEmpty) modelToSelect = null;
        }
      }
      
      // Final fallback: first available model
      modelToSelect ??= allModels.isNotEmpty ? allModels.first : null;

      setState(() {
        _models = allModels;
        _loading = false;
        // Don't set _selectedModel here - let _handleModelChange do it
      });
      
      // Auto-select the model on backend if we found one
      if (modelToSelect != null) {
        debugPrint('🎯 Auto-selecting model: ${modelToSelect.id}');
        await _handleModelChange(modelToSelect);
      }
    } catch (e) {
      debugPrint('❌ Error loading models: $e');
      setState(() {
        _loading = false;
        _error = 'Failed to load models';
      });
    }
  }

  /// Load Bedrock models from settings if credentials are configured
  Future<List<AIModel>> _loadBedrockModelsFromSettings() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      
      // Check if Bedrock is configured (has access key)
      final accessKey = prefs.getString('bedrock_access_key');
      if (accessKey == null || accessKey.isEmpty) {
        return [];
      }
      
      // Load selected models
      final modelsJson = prefs.getString('bedrock_models');
      if (modelsJson == null || modelsJson.isEmpty) {
        return [];
      }
      
      final List<dynamic> modelIds = jsonDecode(modelsJson);
      
      // Convert model IDs to AIModel objects
      final bedrockModels = <AIModel>[];
      for (final modelId in modelIds) {
        if (modelId is String) {
          // Extract model name from ID
          // e.g., "anthropic.claude-sonnet-4-5-20250929-v1:0" -> "Claude Sonnet 4.5"
          final name = _getBedrockModelName(modelId);
          bedrockModels.add(AIModel(
            id: 'bedrock:$modelId',
            provider: 'bedrock',
            name: name,
          ));
        }
      }
      
      debugPrint('✅ Loaded ${bedrockModels.length} Bedrock models from settings');
      return bedrockModels;
    } catch (e) {
      debugPrint('❌ Error loading Bedrock models from settings: $e');
      return [];
    }
  }

  /// Get human-readable name for Bedrock model ID
  String _getBedrockModelName(String modelId) {
    // Map of known Bedrock model IDs to friendly names
    const modelNames = {
      'anthropic.claude-opus-4-1-20250805-v1:0': 'Claude Opus 4.1',
      'anthropic.claude-sonnet-4-5-20250929-v1:0': 'Claude Sonnet 4.5',
      'anthropic.claude-3-5-haiku-20241022-v1:0': 'Claude 3.5 Haiku',
      'deepseek.r1-v1:0': 'DeepSeek-R1',
      'meta.llama3-3-70b-instruct-v1:0': 'Llama 3.3 70B Instruct',
      'openai.gpt-oss-120b-1:0': 'gpt-oss-120b',
    };
    
    return modelNames[modelId] ?? modelId;
  }

  Future<void> _handleModelChange(AIModel? model) async {
    if (model == null || model == _selectedModel) return;

    setState(() {
      _selectedModel = model;
    });

    // Select model on backend (with AWS credentials if needed)
    try {
      // Check if it's a Bedrock model
      final isBedrock = model.provider == 'bedrock';
      
      if (isBedrock) {
        // Load AWS credentials from SharedPreferences
        final prefs = await SharedPreferences.getInstance();
        final awsRegion = prefs.getString('bedrock_region');
        final awsAccessKey = prefs.getString('bedrock_access_key');
        final awsSecretKey = prefs.getString('bedrock_secret_key');
        
        debugPrint('🔍 Loading AWS credentials from SharedPreferences:');
        debugPrint('   Region: ${awsRegion != null ? awsRegion : "NULL"}');
        debugPrint('   Access Key: ${awsAccessKey != null ? "SET (${awsAccessKey.substring(0, 4)}...)" : "NULL"}');
        debugPrint('   Secret Key: ${awsSecretKey != null ? "SET" : "NULL"}');
        
        if (awsRegion == null || awsAccessKey == null || awsSecretKey == null) {
          debugPrint('⚠️ AWS credentials not found in settings for Bedrock model');
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('Please configure AWS credentials in Settings first'),
                backgroundColor: Colors.orange,
                duration: Duration(seconds: 4),
              ),
            );
          }
          // Revert model selection
          setState(() {
            _selectedModel = null;
          });
          return;
        }
        
        debugPrint('✅ Credentials loaded, sending to backend...');
        await _service.selectModel(
          model.id,
          awsRegion: awsRegion,
          awsAccessKeyId: awsAccessKey,
          awsSecretAccessKey: awsSecretKey,
        );
      } else {
        // For non-Bedrock models, just select without credentials
        await _service.selectModel(model.id);
      }
      
      debugPrint('✅ Model ${model.id} selected on backend');
      
      // Save selected model to local storage for persistence
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('last_selected_model', model.id);
      debugPrint('💾 Saved last selected model: ${model.id}');
    } catch (e) {
      debugPrint('❌ Failed to select model on backend: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to select model: $e'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }

    // Notify parent
    widget.onModelChanged?.call(model);
  }

  AIModel? get selectedModel => _selectedModel;

  /// Public method to select a model programmatically
  Future<void> selectModel(AIModel model) async {
    await _handleModelChange(model);
  }

  /// Public method to refresh the model list (e.g., after settings change)
  Future<void> refreshModels() async {
    await _loadModels();
  }

  @override
  Widget build(BuildContext context) {
    // Loading state
    if (_loading) {
      return Container(
        height: 32,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: Colors.grey.shade300, width: 1),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                strokeWidth: 1.5,
                color: Colors.grey.shade600,
              ),
            ),
            const SizedBox(width: 6),
            Text(
              'Loading...',
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey.shade600,
                fontWeight: FontWeight.w400,
              ),
            ),
          ],
        ),
      );
    }

    // Error state
    if (_error != null) {
      return Container(
        height: 32,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: Colors.red.shade300, width: 1),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 14, color: Colors.red.shade600),
            const SizedBox(width: 4),
            InkWell(
              onTap: _loadModels,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                child: Icon(Icons.refresh, size: 14, color: Colors.red.shade600),
              ),
            ),
          ],
        ),
      );
    }

    // Empty state
    if (_models.isEmpty) {
      return Container(
        height: 32,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: Colors.grey.shade300, width: 1),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Text(
          'No models',
          style: TextStyle(
            fontSize: 12,
            color: Colors.grey.shade600,
            fontWeight: FontWeight.w400,
          ),
        ),
      );
    }

    // Normal state with dropdown
    // Calculate width based on longest model name
    final longestName = _models.map((m) => m.name.length).reduce((a, b) => a > b ? a : b);
    final dropdownWidth = ((longestName * 7.5) + 10 + 4 + 18 + 10).clamp(100.0, 300.0);
    
    return Align(
      alignment: Alignment.centerRight,
      child: Container(
        height: 32,
        width: dropdownWidth,
        decoration: BoxDecoration(
          color: Colors.transparent, // Remove background
          // No border - removed the border property
          borderRadius: BorderRadius.circular(16),
        ),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<AIModel>(
            value: _selectedModel,
            items: _models.map((model) {
              return DropdownMenuItem<AIModel>(
                value: model,
                child: Container(
                  width: dropdownWidth - 40, // Width for menu items based on longest name
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Provider label
                      Text(
                        _getProviderLabel(model.provider),
                        style: TextStyle(
                          fontSize: 9,
                          fontWeight: FontWeight.w500,
                          color: Colors.grey.shade500,
                          height: 1.0,
                          letterSpacing: 0.3,
                        ),
                      ),
                      const SizedBox(height: 2),
                      // Model name
                      Text(
                        model.name,
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          color: Colors.black87,
                          height: 1.2,
                          letterSpacing: -0.2,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              );
            }).toList(),
            onChanged: _handleModelChange,
            selectedItemBuilder: (BuildContext context) {
              return _models.map<Widget>((AIModel model) {
                // Simplified view for selected item (no provider label)
                // Right-aligned text
                return Align(
                  alignment: Alignment.centerRight,
                  child: Padding(
                    padding: const EdgeInsets.only(right: 4),
                    child: Text(
                      model.name,
                      style: const TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: Colors.black87,
                        letterSpacing: -0.2,
                      ),
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.right,
                    ),
                  ),
                );
              }).toList();
            },
            icon: Padding(
              padding: const EdgeInsets.only(left: 2),
              child: Icon(
                Icons.expand_more,
                size: 18,
                color: Colors.grey.shade600,
              ),
            ),
            padding: const EdgeInsets.only(left: 10, right: 4),
            isDense: true,
            isExpanded: true,
            borderRadius: BorderRadius.circular(12),
            dropdownColor: Colors.white,
            elevation: 4,
            menuMaxHeight: 300,
          ),
        ),
      ),
    );
  }
  
  /// Get human-readable provider label
  String _getProviderLabel(String provider) {
    switch (provider.toLowerCase()) {
      case 'ollama':
        return 'OLLAMA';
      case 'openai':
        return 'OPENAI';
      case 'bedrock':
        return 'AWS BEDROCK';
      case 'anthropic':
        return 'ANTHROPIC';
      case 'azure':
        return 'AZURE OPENAI';
      case 'vertex':
        return 'GOOGLE VERTEX';
      case 'cohere':
        return 'COHERE';
      default:
        return provider.toUpperCase();
    }
  }
}

