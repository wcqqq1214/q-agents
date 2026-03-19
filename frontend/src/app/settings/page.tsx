'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { api } from '@/lib/api';
import { Eye, EyeOff, Loader2 } from 'lucide-react';

interface APIKeyConfig {
  key: string;
  label: string;
  description: string;
  placeholder: string;
  group: 'llm' | 'embedding' | 'datasource';
}

const apiKeyConfigs: APIKeyConfig[] = [
  {
    key: 'claude_api_key',
    label: 'Claude API Key',
    description: 'Used for LLM-powered analysis and reasoning',
    placeholder: 'sk-ant-...',
    group: 'llm',
  },
  {
    key: 'openai_api_key',
    label: 'OpenAI API Key',
    description: 'Used for text embeddings',
    placeholder: 'sk-...',
    group: 'embedding',
  },
  {
    key: 'polygon_api_key',
    label: 'Polygon API Key',
    description: 'Used for market data and stock information',
    placeholder: 'Your Polygon API key',
    group: 'datasource',
  },
  {
    key: 'tavily_api_key',
    label: 'Tavily API Key',
    description: 'Used for news search and web research',
    placeholder: 'tvly-...',
    group: 'datasource',
  },
];

export default function SettingsPage() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    claude_api_key: '',
    openai_api_key: '',
    polygon_api_key: '',
    tavily_api_key: '',
  });
  const [showPassword, setShowPassword] = useState({
    claude_api_key: false,
    openai_api_key: false,
    polygon_api_key: false,
    tavily_api_key: false,
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await api.getSettings();
      setFormData({
        claude_api_key: data.claude_api_key || '',
        openai_api_key: data.openai_api_key || '',
        polygon_api_key: data.polygon_api_key || '',
        tavily_api_key: data.tavily_api_key || '',
      });
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to load settings',
        variant: 'destructive',
      });
    }
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      await api.updateSettings(formData);
      toast({
        title: 'Success',
        description: 'Settings saved successfully',
      });
      await loadSettings();
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to save settings',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const toggleVisibility = (key: string) => {
    setShowPassword((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleInputChange = (key: string, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const renderPasswordInput = (config: APIKeyConfig) => (
    <div key={config.key} className="space-y-2">
      <Label htmlFor={config.key}>{config.label}</Label>
      <div className="relative">
        <Input
          id={config.key}
          type={showPassword[config.key as keyof typeof showPassword] ? 'text' : 'password'}
          placeholder={config.placeholder}
          value={formData[config.key as keyof typeof formData]}
          onChange={(e) => handleInputChange(config.key, e.target.value)}
          className="pr-10"
        />
        <button
          type="button"
          onClick={() => toggleVisibility(config.key)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
        >
          {showPassword[config.key as keyof typeof showPassword] ? (
            <EyeOff className="h-4 w-4" />
          ) : (
            <Eye className="h-4 w-4" />
          )}
        </button>
      </div>
      <p className="text-sm text-muted-foreground">{config.description}</p>
    </div>
  );

  const llmConfigs = apiKeyConfigs.filter((c) => c.group === 'llm');
  const embeddingConfigs = apiKeyConfigs.filter((c) => c.group === 'embedding');
  const datasourceConfigs = apiKeyConfigs.filter((c) => c.group === 'datasource');

  return (
    <div className="container mx-auto py-8 px-4 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Settings</h1>
        <p className="text-muted-foreground">
          Configure API keys for external services. Changes take effect immediately.
        </p>
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>LLM Configuration</CardTitle>
            <CardDescription>
              Configure the language model used for analysis and reasoning
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {llmConfigs.map(renderPasswordInput)}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Embedding Configuration</CardTitle>
            <CardDescription>
              Configure the embedding model for text processing
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {embeddingConfigs.map(renderPasswordInput)}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Data Source Configuration</CardTitle>
            <CardDescription>
              Configure external data sources for market data and research
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {datasourceConfigs.map(renderPasswordInput)}
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save Configuration
          </Button>
        </div>
      </div>
    </div>
  );
}
