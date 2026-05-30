# llama.cpp and Model Setup

`all2text` does not vendor llama.cpp, GGUF models, projectors, tokenizer assets, or downloaded model
repositories. Keep all of those artifacts outside this repository, for example under
`/data/opt/llama.cpp` and `/data/models/llama_cpp`.

This document describes the integration shape for Jetson/local deployments. The core package remains
usable without llama.cpp; when no OCR/VLM/LLM backend is configured, outputs must keep the truthful
placeholder behavior tested in this repository.

## External Build

Install build tools externally, then clone llama.cpp outside the repo:

```bash
mkdir -p /data/opt
git clone https://github.com/ggml-org/llama.cpp /data/opt/llama.cpp
cd /data/opt/llama.cpp
```

CPU build:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release --target llama-server llama-cli -j"$(nproc)"
```

Jetson CUDA build, when the Jetson image has a compatible CUDA toolchain:

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON
cmake --build build --config Release --target llama-server llama-cli -j"$(nproc)"
```

If CUDA configuration fails, keep the failed build logs outside `all2text`, fix the external
llama.cpp environment, and rebuild there. Do not copy llama.cpp source, build products, or logs into
this repository.

## External Model Files

The devtests context used these model filenames as examples:

- text model: `Qwen2.5-14B-Instruct-Q4_K_M.gguf`
- vision model: `Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf`
- vision projector: `mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf`

These are external artifacts. They are not packaged by `all2text`, not committed to git, and not
downloaded by tests.

Suggested layout:

```text
/data/models/llama_cpp/
  Qwen2.5-14B-Instruct-Q4_K_M.gguf
  Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf
  mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf
```

Download models from the model publisher or an approved internal mirror. A typical Hugging Face CLI
flow is:

```bash
mkdir -p /data/models/llama_cpp
huggingface-cli download <text-model-repo> \
  Qwen2.5-14B-Instruct-Q4_K_M.gguf \
  --local-dir /data/models/llama_cpp
huggingface-cli download <vision-model-repo> \
  Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
  mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf \
  --local-dir /data/models/llama_cpp
```

Record the source repository, license, checksum, and quantization in an external operations log.
Do not put model cards, cached blobs, or download traces under `all2text`.

## Text Server

Run a text-only OpenAI-compatible llama server on a local port:

```bash
/data/opt/llama.cpp/build/bin/llama-server \
  --host 127.0.0.1 \
  --port 8081 \
  -m /data/models/llama_cpp/Qwen2.5-14B-Instruct-Q4_K_M.gguf \
  -c 8192 \
  -ngl 99
```

On memory-constrained Jetson systems, reduce context size or GPU layers:

```bash
/data/opt/llama.cpp/build/bin/llama-server \
  --host 127.0.0.1 \
  --port 8081 \
  -m /data/models/llama_cpp/Qwen2.5-14B-Instruct-Q4_K_M.gguf \
  -c 4096 \
  -ngl 40
```

Health check:

```bash
curl http://127.0.0.1:8081/health
```

Minimal chat check:

```bash
curl http://127.0.0.1:8081/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "local-text",
    "messages": [{"role": "user", "content": "Return the word ready."}],
    "temperature": 0,
    "max_tokens": 8
  }'
```

## Vision Server

Run a separate local server for vision so text and VLM capacity can be managed independently:

```bash
/data/opt/llama.cpp/build/bin/llama-server \
  --host 127.0.0.1 \
  --port 8082 \
  -m /data/models/llama_cpp/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
  --mmproj /data/models/llama_cpp/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf \
  -c 8192 \
  -ngl 99
```

If projector offload is unstable on a specific Jetson build, test with fewer GPU layers or the
llama.cpp projector offload controls documented upstream. Keep the exact server command in an
external runtime log so extraction manifests can be traced to a model/server configuration.

## all2text Integration Contract

Future llama.cpp-backed all2text providers should be optional backends. They should:

- require explicit configuration of base URL, model name/path, timeout, and prompt policy;
- record whether a request was attempted, succeeded, skipped, or failed;
- set `llm_used` or `vlm_used` only when a provider actually returned accepted content;
- preserve source evidence and avoid hallucinated claims;
- store concise provider metadata in `ConversionResult.metadata`;
- leave core placeholder behavior unchanged when the server is unavailable.

Suggested external configuration names:

```bash
export ALL2TEXT_LLAMA_TEXT_BASE_URL=http://127.0.0.1:8081
export ALL2TEXT_LLAMA_TEXT_MODEL=Qwen2.5-14B-Instruct-Q4_K_M.gguf
export ALL2TEXT_LLAMA_VISION_BASE_URL=http://127.0.0.1:8082
export ALL2TEXT_LLAMA_VISION_MODEL=Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf
export ALL2TEXT_LLAMA_VISION_MMPROJ=mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf
```

These variables document the intended contract; the current core package does not require them.

## References

- Official llama.cpp repository: <https://github.com/ggml-org/llama.cpp>
- Official build documentation: <https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md>
- Official server documentation: <https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md>
- Official multimodal documentation: <https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md>
