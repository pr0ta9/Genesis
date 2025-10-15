import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'package:gui/data/services/precedent_service.dart';

// AWS Bedrock Model data
class BedrockModel {
  final String id;
  final String name;
  final List<String> supportedRegions;

  const BedrockModel(this.id, this.name, this.supportedRegions);
}

// Model region support based on AWS Bedrock documentation
// Reference: https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
const List<BedrockModel> bedrockModels = [
  BedrockModel(
    'anthropic.claude-opus-4-1-20250805-v1:0',
    'Claude Opus 4.1',
    ['us-east-1', 'us-west-2', 'ap-northeast-1', 'ap-southeast-2', 'eu-central-1', 'eu-west-1', 'eu-west-2'],
  ),
  BedrockModel(
    'anthropic.claude-sonnet-4-5-20250929-v1:0',
    'Claude Sonnet 4.5',
    ['us-east-1', 'us-west-2', 'ap-northeast-1', 'ap-southeast-1', 'ap-southeast-2', 'eu-central-1', 'eu-west-1', 'eu-west-2'],
  ),
  BedrockModel(
    'anthropic.claude-3-5-haiku-20241022-v1:0',
    'Claude 3.5 Haiku',
    ['us-east-1', 'us-west-2', 'ap-northeast-1', 'ap-southeast-1', 'ap-southeast-2', 'eu-central-1', 'eu-west-1', 'eu-west-2'],
  ),
  BedrockModel(
    'deepseek.r1-v1:0',
    'DeepSeek-R1',
    ['us-east-1', 'us-west-2'],
  ),
  BedrockModel(
    'meta.llama3-3-70b-instruct-v1:0',
    'Llama 3.3 70B Instruct',
    ['us-east-1', 'us-west-2', 'ap-northeast-1', 'ap-south-1', 'ap-southeast-1', 'ap-southeast-2', 'ca-central-1', 'eu-central-1', 'eu-west-1', 'eu-west-2', 'eu-west-3', 'sa-east-1'],
  ),
  BedrockModel(
    'openai.gpt-oss-120b-1:0',
    'gpt-oss-120b',
    ['us-east-1', 'us-west-2'],
  ),
];

// AWS Region data
class AWSRegion {
  final String name;
  final String code;

  const AWSRegion(this.name, this.code);
}

const List<AWSRegion> awsRegions = [
  AWSRegion('US East (Ohio)', 'us-east-2'),
  AWSRegion('US East (N. Virginia)', 'us-east-1'),
  AWSRegion('US West (N. California)', 'us-west-1'),
  AWSRegion('US West (Oregon)', 'us-west-2'),
  AWSRegion('Africa (Cape Town)', 'af-south-1'),
  AWSRegion('Asia Pacific (Hong Kong)', 'ap-east-1'),
  AWSRegion('Asia Pacific (Hyderabad)', 'ap-south-2'),
  AWSRegion('Asia Pacific (Jakarta)', 'ap-southeast-3'),
  AWSRegion('Asia Pacific (Malaysia)', 'ap-southeast-5'),
  AWSRegion('Asia Pacific (Melbourne)', 'ap-southeast-4'),
  AWSRegion('Asia Pacific (Mumbai)', 'ap-south-1'),
  AWSRegion('Asia Pacific (New Zealand)', 'ap-southeast-6'),
  AWSRegion('Asia Pacific (Osaka)', 'ap-northeast-3'),
  AWSRegion('Asia Pacific (Seoul)', 'ap-northeast-2'),
  AWSRegion('Asia Pacific (Singapore)', 'ap-southeast-1'),
  AWSRegion('Asia Pacific (Sydney)', 'ap-southeast-2'),
  AWSRegion('Asia Pacific (Taipei)', 'ap-east-2'),
  AWSRegion('Asia Pacific (Thailand)', 'ap-southeast-7'),
  AWSRegion('Asia Pacific (Tokyo)', 'ap-northeast-1'),
  AWSRegion('Canada (Central)', 'ca-central-1'),
  AWSRegion('Canada West (Calgary)', 'ca-west-1'),
  AWSRegion('Europe (Frankfurt)', 'eu-central-1'),
  AWSRegion('Europe (Ireland)', 'eu-west-1'),
  AWSRegion('Europe (London)', 'eu-west-2'),
  AWSRegion('Europe (Milan)', 'eu-south-1'),
  AWSRegion('Europe (Paris)', 'eu-west-3'),
  AWSRegion('Europe (Spain)', 'eu-south-2'),
  AWSRegion('Europe (Stockholm)', 'eu-north-1'),
  AWSRegion('Europe (Zurich)', 'eu-central-2'),
  AWSRegion('Israel (Tel Aviv)', 'il-central-1'),
  AWSRegion('Mexico (Central)', 'mx-central-1'),
  AWSRegion('Middle East (Bahrain)', 'me-south-1'),
  AWSRegion('Middle East (UAE)', 'me-central-1'),
  AWSRegion('South America (São Paulo)', 'sa-east-1'),
  AWSRegion('AWS GovCloud (US-East)', 'us-gov-east-1'),
  AWSRegion('AWS GovCloud (US-West)', 'us-gov-west-1'),
];

class SettingsPage extends StatefulWidget {
  final VoidCallback onBack;
  final Function(String chatId)? onNavigateToChat;

  const SettingsPage({
    super.key,
    required this.onBack,
    this.onNavigateToChat,
  });

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

enum SettingsTab {
  general,
  provider,
  precedent,
}

class _SettingsPageState extends State<SettingsPage> {
  SettingsTab _selectedTab = SettingsTab.provider;
  
  // Ollama settings
  final TextEditingController _ollamaPortController = TextEditingController();
  
  // Bedrock settings
  final TextEditingController _bedrockAccessKeyController = TextEditingController();
  final TextEditingController _bedrockSecretKeyController = TextEditingController();
  String? _selectedAwsRegion;
  List<String> _selectedBedrockModels = [];
  bool _obscureSecretKey = true; // State for secret key visibility

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      
      setState(() {
        // Load Ollama settings
        _ollamaPortController.text = prefs.getString('ollama_port') ?? '';
        
        // Load Bedrock settings
        _bedrockAccessKeyController.text = prefs.getString('bedrock_access_key') ?? '';
        _bedrockSecretKeyController.text = prefs.getString('bedrock_secret_key') ?? '';
        _selectedAwsRegion = prefs.getString('bedrock_region') ?? 'us-east-1';
        
        // Load selected models (stored as JSON array)
        final modelsJson = prefs.getString('bedrock_models');
        if (modelsJson != null && modelsJson.isNotEmpty) {
          final List<dynamic> decoded = jsonDecode(modelsJson);
          _selectedBedrockModels = decoded.cast<String>();
        } else {
          _selectedBedrockModels = [];
        }
      });
      
      debugPrint('✅ Settings loaded from local storage');
    } catch (e) {
      debugPrint('❌ Error loading settings: $e');
      _loadDefaultSettings();
    }
  }

  void _loadDefaultSettings() {
    _ollamaPortController.text = ''; // Will show placeholder (11434)
    _selectedAwsRegion = 'us-east-1'; // Default region
    _selectedBedrockModels = []; // Default: no models selected
  }

  @override
  void dispose() {
    _ollamaPortController.dispose();
    _bedrockAccessKeyController.dispose();
    _bedrockSecretKeyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: Row(
        children: [
          // Left sidebar for navigation
          Container(
            width: 240,
            decoration: BoxDecoration(
              color: Colors.white,
              border: Border(
                right: BorderSide(color: Colors.grey.shade200, width: 1),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header with back button
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      InkWell(
                        onTap: widget.onBack,
                        borderRadius: BorderRadius.circular(8),
                        child: Container(
                          padding: const EdgeInsets.all(8),
                          child: Icon(
                            Icons.arrow_back,
                            size: 24,
                            color: Colors.grey.shade700,
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Text(
                        'Settings',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                          color: Colors.grey.shade900,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                // Navigation tabs
                _buildNavItem(
                  icon: Icons.tune,
                  label: 'General',
                  tab: SettingsTab.general,
                ),
                _buildNavItem(
                  icon: Icons.cloud_outlined,
                  label: 'Provider',
                  tab: SettingsTab.provider,
                ),
                _buildNavItem(
                  icon: Icons.history,
                  label: 'Precedent',
                  tab: SettingsTab.precedent,
                ),
              ],
            ),
          ),
          
          // Right content area
          Expanded(
            child: _buildContent(),
          ),
        ],
      ),
    );
  }

  Widget _buildNavItem({
    required IconData icon,
    required String label,
    required SettingsTab tab,
  }) {
    final isSelected = _selectedTab == tab;
    return InkWell(
      onTap: () {
        setState(() {
          _selectedTab = tab;
        });
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? Colors.grey.shade100 : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          children: [
            Icon(
              icon,
              size: 18,
              color: isSelected ? Colors.grey.shade900 : Colors.grey.shade600,
            ),
            const SizedBox(width: 12),
            Text(
              label,
              style: TextStyle(
                fontSize: 14,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                color: isSelected ? Colors.grey.shade900 : Colors.grey.shade700,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildContent() {
    switch (_selectedTab) {
      case SettingsTab.general:
        return _buildGeneralSettings();
      case SettingsTab.provider:
        return _buildProviderSettings();
      case SettingsTab.precedent:
        return _buildPrecedentSettings();
    }
  }

  Widget _buildGeneralSettings() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 700),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'General Settings',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w600,
                  color: Colors.grey.shade900,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Configure general application preferences',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey.shade600,
                ),
              ),
              const SizedBox(height: 32),
              // Add general settings here
              Text(
                'Coming soon...',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey.shade500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildProviderSettings() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(32),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 700),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Provider Settings',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w600,
                  color: Colors.grey.shade900,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Configure AI model providers',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey.shade600,
                ),
              ),
              const SizedBox(height: 32),
              
              // Ollama Section
              _buildSectionHeader('Ollama'),
              const SizedBox(height: 16),
              _buildInputField(
                label: 'Port',
                controller: _ollamaPortController,
                placeholder: '11434',
                helperText: 'Port number for Ollama connection',
              ),
              const SizedBox(height: 32),
              
              // Bedrock Section
              _buildSectionHeader('AWS Bedrock'),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.blue.shade200),
                ),
                child: Row(
                  children: [
                    Icon(
                      Icons.info_outline,
                      size: 18,
                      color: Colors.blue.shade700,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        'Please make sure your account has access to the model you selected',
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.blue.shade900,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              _buildInputField(
                label: 'Access Key',
                controller: _bedrockAccessKeyController,
                placeholder: 'Enter your AWS access key',
                obscureText: false,
              ),
              const SizedBox(height: 16),
              _buildSecretKeyField(),
              const SizedBox(height: 16),
              _buildRegionDropdown(),
              const SizedBox(height: 16),
              _buildModelMultiSelect(),
              const SizedBox(height: 32),
              
              // Action buttons
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  // Default button
                  OutlinedButton(
                    onPressed: _resetToDefaultSettings,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.grey.shade700,
                      side: BorderSide(color: Colors.grey.shade300),
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: const Text(
                      'Default',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Save button
                  ElevatedButton(
                    onPressed: _saveProviderSettings,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.black,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: const Text(
                      'Save Settings',
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPrecedentSettings() {
    return _PrecedentSettingsContent(
      onNavigateToChat: widget.onNavigateToChat,
    );
  }

  Widget _buildSectionHeader(String title) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Colors.grey.shade900,
          ),
        ),
        const SizedBox(height: 8),
        Container(
          height: 2,
          width: 40,
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(1),
          ),
        ),
      ],
    );
  }

  Widget _buildInputField({
    required String label,
    required TextEditingController controller,
    required String placeholder,
    String? helperText,
    bool obscureText = false,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: Colors.grey.shade900,
          ),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: controller,
          obscureText: obscureText,
          decoration: InputDecoration(
            hintText: placeholder,
            hintStyle: TextStyle(color: Colors.grey.shade400),
            helperText: helperText,
            helperStyle: TextStyle(
              fontSize: 12,
              color: Colors.grey.shade600,
            ),
            filled: true,
            fillColor: Colors.grey.shade50,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(color: Colors.grey.shade300),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(color: Colors.grey.shade300),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: Colors.black, width: 2),
            ),
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 12,
            ),
          ),
          style: TextStyle(
            fontSize: 14,
            color: Colors.grey.shade900,
          ),
        ),
      ],
    );
  }

  Widget _buildSecretKeyField() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Secret Access Key',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: Colors.grey.shade900,
          ),
        ),
        const SizedBox(height: 8),
        TextField(
          controller: _bedrockSecretKeyController,
          obscureText: _obscureSecretKey,
          decoration: InputDecoration(
            hintText: 'Enter your AWS secret access key',
            hintStyle: TextStyle(color: Colors.grey.shade400),
            filled: true,
            fillColor: Colors.grey.shade50,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(color: Colors.grey.shade300),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(color: Colors.grey.shade300),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: Colors.black, width: 2),
            ),
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 12,
            ),
            suffixIcon: IconButton(
              icon: Icon(
                _obscureSecretKey ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                size: 20,
                color: Colors.grey.shade600,
              ),
              onPressed: () {
                setState(() {
                  _obscureSecretKey = !_obscureSecretKey;
                });
              },
              tooltip: _obscureSecretKey ? 'Show secret key' : 'Hide secret key',
            ),
          ),
          style: TextStyle(
            fontSize: 14,
            color: Colors.grey.shade900,
          ),
        ),
      ],
    );
  }

  // Helper method to get regions that have at least one model
  List<AWSRegion> _getRegionsWithModels() {
    return awsRegions.where((region) {
      // Check if any model supports this region
      return bedrockModels.any((model) => model.supportedRegions.contains(region.code));
    }).toList();
  }

  // Helper method to count models available in a region
  int _getModelCountForRegion(String regionCode) {
    return bedrockModels.where((model) => model.supportedRegions.contains(regionCode)).length;
  }

  Widget _buildRegionDropdown() {
    final availableRegions = _getRegionsWithModels();
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'AWS Region',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: Colors.grey.shade900,
          ),
        ),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(
          value: _selectedAwsRegion,
          decoration: InputDecoration(
            filled: true,
            fillColor: Colors.grey.shade50,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(color: Colors.grey.shade300),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: BorderSide(color: Colors.grey.shade300),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(8),
              borderSide: const BorderSide(color: Colors.black, width: 2),
            ),
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 12,
            ),
          ),
          items: availableRegions.map((region) {
            final modelCount = _getModelCountForRegion(region.code);
            return DropdownMenuItem<String>(
              value: region.code,
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      region.name,
                      style: TextStyle(
                        fontSize: 14,
                        color: Colors.grey.shade900,
                      ),
                    ),
                  ),
                  Text(
                    '($modelCount ${modelCount == 1 ? 'model' : 'models'})',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade600,
                    ),
                  ),
                ],
              ),
            );
          }).toList(),
          onChanged: (value) {
            setState(() {
              _selectedAwsRegion = value;
            });
          },
          icon: Icon(Icons.arrow_drop_down, color: Colors.grey.shade700),
          dropdownColor: Colors.white,
          isExpanded: true,
        ),
      ],
    );
  }

  Widget _buildModelMultiSelect() {
    // Filter models based on selected region
    final availableModels = bedrockModels.where((model) {
      return _selectedAwsRegion != null && model.supportedRegions.contains(_selectedAwsRegion);
    }).toList();

    // Remove any selected models that are no longer available in the current region
    _selectedBedrockModels.removeWhere((modelId) {
      return !availableModels.any((m) => m.id == modelId);
    });

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              'Models',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: Colors.grey.shade900,
              ),
            ),
            const SizedBox(width: 8),
            Text(
              '(${_selectedBedrockModels.length} selected)',
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey.shade600,
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        if (availableModels.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4, bottom: 4),
            child: Text(
              'No models available in selected region',
              style: TextStyle(
                fontSize: 12,
                color: Colors.orange.shade700,
                fontStyle: FontStyle.italic,
              ),
            ),
          )
        else
          Text(
            '${availableModels.length} models available in this region',
            style: TextStyle(
              fontSize: 12,
              color: Colors.grey.shade600,
            ),
          ),
        const SizedBox(height: 8),
        Container(
          decoration: BoxDecoration(
            color: Colors.grey.shade50,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.grey.shade300),
          ),
          child: availableModels.isEmpty
              ? Padding(
                  padding: const EdgeInsets.all(16),
                  child: Center(
                    child: Text(
                      'Select a region to view available models',
                      style: TextStyle(
                        fontSize: 13,
                        color: Colors.grey.shade500,
                      ),
                    ),
                  ),
                )
              : Column(
                  children: availableModels.map((model) {
                    final isSelected = _selectedBedrockModels.contains(model.id);
                    return InkWell(
                      onTap: () {
                        setState(() {
                          if (isSelected) {
                            _selectedBedrockModels.remove(model.id);
                          } else {
                            _selectedBedrockModels.add(model.id);
                          }
                        });
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        decoration: BoxDecoration(
                          border: Border(
                            bottom: model != availableModels.last
                                ? BorderSide(color: Colors.grey.shade200)
                                : BorderSide.none,
                          ),
                        ),
                        child: Row(
                          children: [
                            Container(
                              width: 20,
                              height: 20,
                              decoration: BoxDecoration(
                                color: isSelected ? Colors.black : Colors.white,
                                border: Border.all(
                                  color: isSelected ? Colors.black : Colors.grey.shade400,
                                  width: 2,
                                ),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: isSelected
                                  ? const Icon(
                                      Icons.check,
                                      size: 14,
                                      color: Colors.white,
                                    )
                                  : null,
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Text(
                                model.name,
                                style: TextStyle(
                                  fontSize: 14,
                                  color: Colors.grey.shade900,
                                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }).toList(),
                ),
        ),
      ],
    );
  }

  Future<void> _resetToDefaultSettings() async {
    setState(() {
      _loadDefaultSettings();
      _bedrockAccessKeyController.clear();
      _bedrockSecretKeyController.clear();
    });

    // Clear from storage
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('ollama_port');
      await prefs.remove('bedrock_access_key');
      await prefs.remove('bedrock_secret_key');
      await prefs.setString('bedrock_region', 'us-east-1');
      await prefs.remove('bedrock_models');
      debugPrint('🗑️ Settings cleared from local storage');
    } catch (e) {
      debugPrint('❌ Error clearing settings: $e');
    }

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Settings reset to default'),
          backgroundColor: Colors.orange,
          duration: Duration(seconds: 2),
        ),
      );
    }
  }

  Future<void> _saveProviderSettings() async {
    final ollamaPort = _ollamaPortController.text;
    final accessKey = _bedrockAccessKeyController.text;
    final secretKey = _bedrockSecretKeyController.text;
    final region = _selectedAwsRegion;
    final models = _selectedBedrockModels;

    try {
      final prefs = await SharedPreferences.getInstance();
      
      // Save Ollama settings
      if (ollamaPort.isNotEmpty) {
        await prefs.setString('ollama_port', ollamaPort);
      } else {
        await prefs.remove('ollama_port');
      }
      
      // Save Bedrock settings
      if (accessKey.isNotEmpty) {
        await prefs.setString('bedrock_access_key', accessKey);
      } else {
        await prefs.remove('bedrock_access_key');
      }
      
      if (secretKey.isNotEmpty) {
        await prefs.setString('bedrock_secret_key', secretKey);
      } else {
        await prefs.remove('bedrock_secret_key');
      }
      
      if (region != null) {
        await prefs.setString('bedrock_region', region);
      }
      
      // Save selected models as JSON array
      if (models.isNotEmpty) {
        await prefs.setString('bedrock_models', jsonEncode(models));
      } else {
        await prefs.remove('bedrock_models');
      }
      
      debugPrint('💾 Settings saved to local storage:');
      debugPrint('  Ollama Port: ${ollamaPort.isEmpty ? "11434 (default)" : ollamaPort}');
      debugPrint('  Bedrock Access Key: ${accessKey.isNotEmpty ? "[SET]" : "[NOT SET]"}');
      debugPrint('  Bedrock Secret Key: ${secretKey.isNotEmpty ? "[SET]" : "[NOT SET]"}');
      debugPrint('  AWS Region: $region');
      debugPrint('  Bedrock Models (${models.length}): $models');

      // Show success message
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Provider settings saved successfully (${models.length} models selected)'),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    } catch (e) {
      debugPrint('❌ Error saving settings: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to save settings: $e'),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    }
  }
}

// Precedent Settings Content Widget
class _PrecedentSettingsContent extends StatefulWidget {
  final Function(String chatId)? onNavigateToChat;

  const _PrecedentSettingsContent({
    Key? key,
    this.onNavigateToChat,
  }) : super(key: key);

  @override
  State<_PrecedentSettingsContent> createState() => _PrecedentSettingsContentState();
}

class _PrecedentSettingsContentState extends State<_PrecedentSettingsContent> {
  final PrecedentService _service = const PrecedentService();
  List<Map<String, dynamic>> _precedents = [];
  Set<String> _selectedUuids = {};
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadPrecedents();
  }

  Future<void> _loadPrecedents() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final precedents = await _service.fetchPrecedents();
      setState(() {
        _precedents = precedents;
        _loading = false;
        _selectedUuids.clear();
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _error = 'Failed to load precedents: $e';
      });
    }
  }

  Future<void> _deleteSelected() async {
    if (_selectedUuids.isEmpty) return;

    // Show confirmation dialog
    final confirmed = await _showConfirmationDialog(
      title: 'Delete Selected Precedents',
      message: 'Are you sure you want to delete ${_selectedUuids.length} selected precedent(s)? This action cannot be undone.',
    );

    if (!confirmed) return;

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      await _service.deletePrecedents(_selectedUuids.toList());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Deleted ${_selectedUuids.length} precedent(s) successfully'),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 2),
          ),
        );
      }
      await _loadPrecedents();
    } catch (e) {
      setState(() {
        _loading = false;
        _error = 'Failed to delete precedents: $e';
      });
    }
  }

  Future<void> _deleteAll() async {
    if (_precedents.isEmpty) return;

    // Show confirmation dialog
    final confirmed = await _showConfirmationDialog(
      title: 'Delete All Precedents',
      message: 'Are you sure you want to delete ALL ${_precedents.length} precedents? This action cannot be undone.',
      isDangerous: true,
    );

    if (!confirmed) return;

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      await _service.deleteAllPrecedents();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('All precedents deleted successfully'),
            backgroundColor: Colors.green,
            duration: Duration(seconds: 2),
          ),
        );
      }
      await _loadPrecedents();
    } catch (e) {
      setState(() {
        _loading = false;
        _error = 'Failed to delete all precedents: $e';
      });
    }
  }

  Future<bool> _showConfirmationDialog({
    required String title,
    required String message,
    bool isDangerous = false,
  }) async {
    final result = await showDialog<bool>(
      context: context,
      barrierColor: Colors.black54,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        title: Text(
          title,
          style: TextStyle(
            color: Colors.grey.shade900,
            fontWeight: FontWeight.w600,
          ),
        ),
        content: Text(
          message,
          style: TextStyle(
            color: Colors.grey.shade700,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            style: TextButton.styleFrom(
              foregroundColor: Colors.grey.shade700,
            ),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: ElevatedButton.styleFrom(
              backgroundColor: isDangerous ? Colors.grey.shade900 : Colors.black,
              foregroundColor: Colors.white,
            ),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    return result ?? false;
  }

  void _showPathVisualization(String objective, List<dynamic>? path) {
    showDialog(
      context: context,
      barrierColor: Colors.black54,
      builder: (context) => Dialog(
        backgroundColor: Colors.white,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        child: Container(
          width: 600,
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      'Workflow Path',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                        color: Colors.grey.shade900,
                      ),
                    ),
                  ),
                  IconButton(
                    icon: Icon(Icons.close, color: Colors.grey.shade700),
                    onPressed: () => Navigator.of(context).pop(),
                    tooltip: 'Close',
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                objective,
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.grey.shade600,
                ),
              ),
              const SizedBox(height: 24),
              
              // Path visualization
              if (path == null || path.isEmpty)
                Container(
                  padding: const EdgeInsets.all(32),
                  decoration: BoxDecoration(
                    color: Colors.grey.shade50,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.grey.shade200),
                  ),
                  child: Center(
                    child: Text(
                      'No path data available',
                      style: TextStyle(color: Colors.grey.shade600),
                    ),
                  ),
                )
              else
                Flexible(
                  child: SingleChildScrollView(
                    child: Column(
                      children: [
                        for (int i = 0; i < path.length; i++)
                          _buildPathStep(i + 1, path[i] as Map<String, dynamic>, i == path.length - 1),
                      ],
                    ),
                  ),
                ),
              
              const SizedBox(height: 24),
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  style: TextButton.styleFrom(
                    foregroundColor: Colors.grey.shade900,
                  ),
                  child: const Text('Close'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPathStep(int stepNumber, Map<String, dynamic> step, bool isLast) {
    final name = step['name']?.toString() ?? 'Unknown';
    String description = step['description']?.toString() ?? '';
    
    // Extract only the description part (before "Args:")
    if (description.contains('Args:')) {
      description = description.substring(0, description.indexOf('Args:')).trim();
    }
    // Also handle other common parameter section markers
    if (description.contains('\n\n')) {
      // Take only the first paragraph (usually the main description)
      description = description.split('\n\n').first.trim();
    }
    
    return Column(
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Step number circle
            Container(
              width: 32,
              height: 32,
              decoration: const BoxDecoration(
                color: Colors.black,
                shape: BoxShape.circle,
              ),
              child: Center(
                child: Text(
                  stepNumber.toString(),
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 16),
            // Step content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: Colors.grey.shade900,
                    ),
                  ),
                  if (description.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      description,
                      style: TextStyle(
                        fontSize: 13,
                        color: Colors.grey.shade600,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
        if (!isLast)
          Padding(
            padding: const EdgeInsets.only(left: 15),
            child: Container(
              width: 2,
              height: 32,
              color: Colors.grey.shade300,
            ),
          ),
      ],
    );
  }

  void _navigateToChat(String? chatId) {
    if (chatId == null) return;
    
    if (widget.onNavigateToChat != null) {
      widget.onNavigateToChat!(chatId);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Navigate to chat: $chatId'),
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.topCenter,
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 700),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Precedent Management',
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.w600,
                          color: Colors.grey.shade900,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Manage saved workflow precedents',
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.grey.shade600,
                        ),
                      ),
                    ],
                  ),
                  if (!_loading)
                    IconButton(
                      icon: const Icon(Icons.refresh),
                      onPressed: _loadPrecedents,
                      tooltip: 'Refresh',
                    ),
                ],
              ),
              const SizedBox(height: 32),

              // Error display
              if (_error != null)
                Container(
                  padding: const EdgeInsets.all(12),
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.grey.shade300),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.error_outline, color: Colors.grey.shade700),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          _error!,
                          style: TextStyle(color: Colors.grey.shade900),
                        ),
                      ),
                    ],
                  ),
                ),

              // Loading state
              if (_loading)
                const Center(
                  child: Padding(
                    padding: EdgeInsets.all(32),
                    child: CircularProgressIndicator(),
                  ),
                ),

              // Content
              if (!_loading) ...[
                // Action buttons
                Row(
                  children: [
                    ElevatedButton.icon(
                      onPressed: _selectedUuids.isEmpty ? null : _deleteSelected,
                      icon: const Icon(Icons.delete_outline, size: 18),
                      label: Text('Delete Selected (${_selectedUuids.length})'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.orange,
                        foregroundColor: Colors.white,
                        disabledBackgroundColor: Colors.grey.shade300,
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      ),
                    ),
                    const SizedBox(width: 12),
                    OutlinedButton.icon(
                      onPressed: _precedents.isEmpty ? null : _deleteAll,
                      icon: const Icon(Icons.delete_forever, size: 18),
                      label: const Text('Delete All'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.red,
                        side: BorderSide(color: Colors.red.shade300),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 24),

                // Precedent count
                Text(
                  '${_precedents.length} precedent(s) stored',
                  style: TextStyle(
                    fontSize: 13,
                    color: Colors.grey.shade600,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 12),

                // Precedent list
                if (_precedents.isEmpty)
                  Container(
                    padding: const EdgeInsets.all(32),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.grey.shade200),
                    ),
                    child: Center(
                      child: Column(
                        children: [
                          Icon(Icons.history, size: 48, color: Colors.grey.shade400),
                          const SizedBox(height: 16),
                          Text(
                            'No precedents saved yet',
                            style: TextStyle(
                              fontSize: 14,
                              color: Colors.grey.shade600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  )
                else
                  Container(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      border: Border.all(color: Colors.grey.shade200),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: ListView.separated(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: _precedents.length,
                      separatorBuilder: (context, index) => Divider(
                        height: 1,
                        color: Colors.grey.shade200,
                      ),
                      itemBuilder: (context, index) {
                        final precedent = _precedents[index];
                        final uuid = precedent['uuid'] as String;
                        final properties = precedent['properties'] as Map<String, dynamic>?;
                        final objective = properties?['objective']?.toString() ?? 'Unknown objective';
                        final path = properties?['path'] as List<dynamic>?;
                        final chatId = precedent['chat_id'] as String?;
                        final isSelected = _selectedUuids.contains(uuid);

                        return InkWell(
                          onTap: () {
                            setState(() {
                              if (isSelected) {
                                _selectedUuids.remove(uuid);
                              } else {
                                _selectedUuids.add(uuid);
                              }
                            });
                          },
                          child: Container(
                            padding: const EdgeInsets.all(16),
                            child: Row(
                              children: [
                                // Checkbox
                                Container(
                                  width: 20,
                                  height: 20,
                                  decoration: BoxDecoration(
                                    color: isSelected ? Colors.black : Colors.white,
                                    border: Border.all(
                                      color: isSelected ? Colors.black : Colors.grey.shade400,
                                      width: 2,
                                    ),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: isSelected
                                      ? const Icon(
                                          Icons.check,
                                          size: 14,
                                          color: Colors.white,
                                        )
                                      : null,
                                ),
                                const SizedBox(width: 16),
                                // Content
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        objective,
                                        style: TextStyle(
                                          fontSize: 14,
                                          fontWeight: FontWeight.w600,
                                          color: Colors.grey.shade900,
                                        ),
                                        maxLines: 2,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        'UUID: ${uuid.substring(0, 8)}...',
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: Colors.grey.shade600,
                                          fontFamily: 'monospace',
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                // Three-dot menu
                                PopupMenuButton<String>(
                                  icon: Icon(Icons.more_vert, color: Colors.grey.shade600),
                                  tooltip: 'More options',
                                  onSelected: (value) {
                                    if (value == 'view_path') {
                                      _showPathVisualization(objective, path);
                                    } else if (value == 'go_to_chat') {
                                      _navigateToChat(chatId);
                                    }
                                  },
                                  itemBuilder: (context) => [
                                    const PopupMenuItem(
                                      value: 'view_path',
                                      child: Row(
                                        children: [
                                          Icon(Icons.route, size: 18),
                                          SizedBox(width: 12),
                                          Text('View Path'),
                                        ],
                                      ),
                                    ),
                                    if (chatId != null)
                                      const PopupMenuItem(
                                        value: 'go_to_chat',
                                        child: Row(
                                          children: [
                                            Icon(Icons.chat_bubble_outline, size: 18),
                                            SizedBox(width: 12),
                                            Text('Go to Chat'),
                                          ],
                                        ),
                                      ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
              ],
          ],
        ),
      ),
      ),
    );
  }
}
