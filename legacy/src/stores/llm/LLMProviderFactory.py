from .LLMEnums import LLMEnum
from .providers import OpenAIProvider, CoHereProvider
class LLMProviderFactory:
  def __init__(self, config: dict):
    self.config = config
    
  def create(self, provider: str):
    
    if provider == LLMEnum.OPENAI.value:
      return OpenAIProvider(
        api_key=self.config.OPEN_API_KEY,
        api_url = self.config.OPEN_API_URL,
        default_input_max_characters = self.config.DEFAULT_INPUT_MAX_CHARACTERS,
        default_generation_output_tokens = self.config.DEFAULT_GENERATION_OUTPUT_TOKENS,
        default_generation_temperature = self.config.DEFAULT_GENERATION_TEMPERATURE)
    
    if provider == LLMEnum.COHERE.value:
      return CoHereProvider(
        api_key=self.config.COHERE_API_KEY,
        default_input_max_characters = self.config.DEFAULT_INPUT_MAX_CHARACTERS,
        default_generation_output_tokens = self.config.DEFAULT_GENERATION_OUTPUT_TOKENS,
        default_generation_temperature = self.config.DEFAULT_GENERATION_TEMPERATURE)
    
    return None