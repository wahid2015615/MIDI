Place the GGUF weight file in this folder (required for TEXT mode only):

  Qwen3-4B-Q4_K_M.gguf

Full path:
  MIDI/backend/models/Qwen3-4B-Q4_K_M.gguf

Chords and Notes modes do not need this file — they are deterministic.

Optional: set LOCAL_MODEL_PATH in backend/.env if the file is elsewhere.

Do not commit the .gguf file to git (large binary).
