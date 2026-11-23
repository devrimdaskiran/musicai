#!/usr/bin/env bash
# ACE-Step 1.5'i CPU'lu GitHub makinesine kurar (GPU gerekmez). Model dosyaları ilk çalışmada
# Hugging Face'ten ace/checkpoints/ içine iner ve workflow önbelleğinde saklanır.
set -euo pipefail
ACE_COMMIT="${ACE_COMMIT:-ca1e85fe9430179831e6bc6be790c332190a3866}"
if [ ! -d ace/acestep ]; then
  mkdir -p ace && cd ace
  git init -q && git remote add origin https://github.com/ACE-Step/ACE-Step-1.5
  git fetch -q --depth 1 origin "$ACE_COMMIT" && git checkout -q FETCH_HEAD
  cd ..
fi
pip install -q torch==2.10.0 torchaudio==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cpu
pip install -q "transformers>=4.51.0,<4.58.0" "diffusers>=0.37.0" "scipy>=1.10.1" "soundfile>=0.13.1" loguru \
  "einops>=0.8.1" "accelerate>=1.12.0" "numba>=0.63.1" "vector-quantize-pytorch>=1.27.15" \
  "torchao>=0.16.0,<0.17.0" toml diskcache modelscope huggingface_hub safetensors xxhash \
  "pytorch-wavelets>=1.3.0" "pywavelets>=1.9.0" matplotlib "peft>=0.18.0" typer-slim "setuptools<72" torchcodec
python -c "import torch; print('torch', torch.__version__, 'threads', torch.get_num_threads())"
