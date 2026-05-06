import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("NVIDIA_API_KEY")
print(f"Key: {key}")
if key:
    print(f"Starts with quote: {key.startswith(chr(34))}")
