# J.A.R.V.I.S. 2.0

J.A.R.V.I.S. 2.0 is a clean implementation of the updated "Body-Part" architecture.
The project is split into a central Mind, identity-focused Heart, specialized Agents,
and a small MCP-style system tool layer.

## Architecture

- `core/mind.py`: central reasoning, delegation, self-awareness, and the background consciousness loop.
- `core/heart.py`: identity state, digital footprint, life-stream context, and assistant-friend personality.
- `core/llm_client.py`: hybrid CPU/GPU/cloud model routing with provider registration hooks.
- `agents/`: Memory, Coding, Vision, Monitoring, and Parallel agents.
- `audio/fish_speech.py`: optional Fish Speech emotional TTS adapter for human-like voice output.
- `tools/system_mcp.py`: read/write scoped tool registry for safe multi-agent coordination.
- `main_async.py`: interactive async entrypoint.

## Voice And Emotion

Whisper-style STT can remain the listening layer. Fish Speech is wired as the
speaking layer through `VoiceAgent`, which asks `Heart` for the current emotion
and converts it into Fish Speech inline style tags such as `[excited]`,
`[whisper]`, `[sad]`, or `[professional broadcast tone]`.

To connect a local Fish Speech API server later:

```powershell
$env:JARVIS_FISH_SPEECH_ENABLED="1"
$env:JARVIS_FISH_SPEECH_URL="http://127.0.0.1:8080"
python main_async.py
```

## Run

```powershell
python main_async.py
```

## Test

```powershell
python -m unittest discover
```

## Notes

External services such as Gmail, GitHub, Hugging Face, NVIDIA, Ollama, WhatsApp,
Netflix, and browser history are represented as explicit integration boundaries.
Fish Speech is also optional and disabled by default. The scaffold does not
access private accounts, external servers, or hardware automatically.
