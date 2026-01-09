"""
Configuration Parser for AI-Trader Orchestrator

Parses the root config.yml file and provides strongly-typed access to all settings.
Uses Pydantic for validation and type safety.
"""

from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field, field_validator
import yaml
import re


class ModelConfig(BaseModel):
    """Parsed model configuration"""
    model: str
    api_base: str
    api_key: str

    @classmethod
    def from_string(cls, config_string: str) -> "ModelConfig":
        """
        Parse model configuration from string format:
        "model: [NAME]; api_base: [URL]; api_key: [KEY]"
        """
        pattern = r'model:\s*([^;]+);\s*api_base:\s*([^;]+);\s*api_key:\s*(.+)'
        match = re.match(pattern, config_string.strip())
        
        if not match:
            raise ValueError(f"Invalid model config format: {config_string}")
        
        return cls(
            model=match.group(1).strip(),
            api_base=match.group(2).strip(),
            api_key=match.group(3).strip()
        )


class ServiceConfig(BaseModel):
    """Parsed service configuration"""
    url: str
    token: Optional[str] = None
    api_key: Optional[str] = None

    @classmethod
    def from_string(cls, config_string: str) -> "ServiceConfig":
        """
        Parse service configuration from string format:
        "url: [URL]; token: [TOKEN]" or "url: [URL]; api_key: [KEY]"
        """
        parts = {}
        for item in config_string.split(';'):
            item = item.strip()
            if ':' in item:
                key, value = item.split(':', 1)
                parts[key.strip()] = value.strip()
        
        if 'url' not in parts:
            raise ValueError(f"Service config must contain 'url': {config_string}")
        
        return cls(
            url=parts['url'],
            token=parts.get('token'),
            api_key=parts.get('api_key')
        )


class KuCoinConfig(BaseModel):
    """KuCoin exchange configuration"""
    api_key: str
    api_secret: str
    api_passphrase: str
    sandbox: bool = True


class DatabaseConfig(BaseModel):
    """Database configuration"""
    type: str = "sqlite"
    path: Optional[str] = "orchestrator/data/orchestrator.db"
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None


class OrchestratorConfig(BaseModel):
    """Orchestrator-specific settings"""
    ui_port: int = 3000
    api_port: int = 8080
    max_concurrent_bots: int = 10
    default_bot_image: str = "freqtrade/freqtrade:stable"
    auto_restart: bool = True


class AITraderConfig(BaseModel):
    """Main configuration model"""
    services: Dict[str, str] = Field(default_factory=dict)
    models: Dict[str, str] = Field(default_factory=dict)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    kucoin: Optional[KuCoinConfig] = None
    
    _services_parsed: Dict[str, ServiceConfig] = {}
    _models_parsed: Dict[str, ModelConfig] = {}

    def parse_services(self):
        """Parse service configurations"""
        for name, config_str in self.services.items():
            try:
                self._services_parsed[name] = ServiceConfig.from_string(config_str)
            except Exception as e:
                raise ValueError(f"Error parsing service '{name}': {e}")

    def parse_models(self):
        """Parse model configurations"""
        for name, config_str in self.models.items():
            try:
                self._models_parsed[name] = ModelConfig.from_string(config_str)
            except Exception as e:
                raise ValueError(f"Error parsing model '{name}': {e}")

    def get_service(self, name: str) -> ServiceConfig:
        """Get parsed service configuration"""
        if not self._services_parsed:
            self.parse_services()
        
        if name not in self._services_parsed:
            raise KeyError(f"Service '{name}' not found in configuration")
        
        return self._services_parsed[name]

    def get_model(self, name: str) -> ModelConfig:
        """Get parsed model configuration"""
        if not self._models_parsed:
            self.parse_models()
        
        if name not in self._models_parsed:
            raise KeyError(f"Model '{name}' not found in configuration")
        
        return self._models_parsed[name]

    def get_fallback_model(self) -> Optional[ModelConfig]:
        """Get fallback model if configured"""
        try:
            return self.get_model('fallback')
        except KeyError:
            return None


def load_config(config_path: str = "config.yml") -> AITraderConfig:
    """
    Load and parse configuration from YAML file
    
    Args:
        config_path: Path to config.yml file (relative to project root)
    
    Returns:
        Parsed AITraderConfig instance
    """
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    config = AITraderConfig(**config_data)
    
    # Pre-parse services and models
    config.parse_services()
    config.parse_models()
    
    return config


# Singleton instance for global access
_config_instance: Optional[AITraderConfig] = None


def get_config() -> AITraderConfig:
    """Get global configuration instance (singleton pattern)"""
    global _config_instance
    
    if _config_instance is None:
        _config_instance = load_config()
    
    return _config_instance


def reload_config(config_path: str = "config.yml"):
    """Reload configuration from file"""
    global _config_instance
    _config_instance = load_config(config_path)


if __name__ == "__main__":
    # Example usage
    config = load_config()
    
    print("=== Services ===")
    for service_name in config.services.keys():
        service = config.get_service(service_name)
        print(f"{service_name}: {service.url}")
    
    print("\n=== Models ===")
    for model_name in config.models.keys():
        model = config.get_model(model_name)
        print(f"{model_name}: {model.model} @ {model.api_base}")
