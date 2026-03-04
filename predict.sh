#!/bin/bash

# Copyright 2024 ByteDance and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

export PROTENIX_ROOT_DIR="/apps/Protenix"

# Usage: predict.sh <input_dir> <output_dir>
# Input: directory with *.json (e.g. inputs/*.json).
input_dir="${1:?Usage: predict.sh <input_dir> <output_dir>}"
out_dir="${2:?Usage: predict.sh <input_dir> <output_dir>}"
parallel_jobs=8

shopt -s nullglob
# Exclude files ending with -final-updated.json and -update-msa.json
jsons=()
for f in "${input_dir}"/*.json; do
    [[ ! -e "$f" ]] && continue
    [[ "$f" == *-final-updated.json ]] && continue
    [[ "$f" == *-update-msa.json ]] && continue
    jsons+=("$f")
done
if [[ ${#jsons[@]} -eq 0 ]]; then
    echo "No suitable *.json in ${input_dir}" >&2
    exit 1
fi

# Skip if output already has predicted structure (resume after cancel).
already_done() {
    local o="$1"
    [[ -d "$o" ]] && find "$o" -name "*.cif" -type f 2>/dev/null | grep -q .
}

echo "Predict: ${#jsons[@]} JSON(s), up to ${parallel_jobs} in parallel (skip existing)."

run_one() {
    local j="$1" o="$2"
    mkdir -p "$o"
    protenix pred -i "$j" -o "$o" \
        --seeds 101 --model_name protenix_base_20250630_v1.0.0 \
        --use_msa true --use_template true --use_default_params false \
        --sample 5 --step 200 --cycle 10
}

running=0
for json in "${jsons[@]}"; do
    base="${json##*/}"
    out_sub="${out_dir}/${base%.json}"
    if already_done "$out_sub"; then
        echo "Skip (done): $base"
        continue
    fi
    run_one "$json" "$out_sub" &
    ((running++)) || true
    if ((running >= parallel_jobs)); then
        # Wait for any one job to finish, then immediately start a new one.
        wait -n
        ((running--)) || true
    fi
done
# Wait for all remaining jobs to finish.
wait
