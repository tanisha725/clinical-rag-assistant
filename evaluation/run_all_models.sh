#!/bin/bash
# Runs the evaluation harness for all 3 models, switching OLLAMA_MODEL in
# .env and restarting llm_service between each (fast: env var only, no
# rebuild needed since config.py reads it via os.getenv at import time).
#
# Run this ON the EC2 host, from ~/idt_project:
#   bash evaluation/run_all_models.sh
set -e

cd "$(dirname "$0")/.."

declare -A MODELS=(
  ["codellama_stub"]="qwen2.5-coder:1.5b-instruct"
  ["llama32_1b"]="llama3.2:1b-instruct-q4_K_M"
  ["qwen25_0.5b"]="qwen2.5:0.5b-instruct"
)

for label in "${!MODELS[@]}"; do
  model="${MODELS[$label]}"
  echo "=================================================="
  echo "Switching to model: $model (label: $label)"
  echo "=================================================="

  sed -i "s|^OLLAMA_MODEL=.*|OLLAMA_MODEL=$model|" .env
  sudo docker compose -f docker-compose.aws-free-tier.yml up -d llm_service

  echo "Waiting for llm_service to report model_pulled=true..."
  for i in $(seq 1 30); do
    ready=$(curl -s http://localhost:8000/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('downstream',{}).get('llm_service',{}).get('model_pulled', False))" 2>/dev/null)
    if [ "$ready" = "True" ]; then
      break
    fi
    sleep 2
  done
  sleep 3

  cd evaluation
  python3 run_eval.py --model-label "$label"
  cd ..

  echo "Finished $label."
done

echo "All models evaluated. Results in evaluation/results/raw/"
