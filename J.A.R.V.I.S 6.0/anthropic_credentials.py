import os
import openai

# Set API key
openai.api_key = os.environ['OPENAI_API_KEY']

# Obtain Anthropic credentials
anthropic_credentials = openai.AnthropicCredentials()

# Print credentials
print(anthropic_credentials)