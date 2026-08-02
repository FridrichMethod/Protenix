# Protenix (fork)

Fork of [bytedance/Protenix](https://github.com/bytedance/Protenix) — an open-source AlphaFold3 reproduction for
biomolecular structure prediction. `origin` is `FridrichMethod/Protenix`, `upstream` is `bytedance/Protenix`.
Work happens on `dev`; `main` tracks upstream. Package version `2.0.0` (`protenix/version.py`).

## Environment

Everything runs in the **`protenix` conda env**, which has the package installed **editable** — `import protenix`
resolves to this working tree, so edits take effect without reinstalling.

```bash
conda activate protenix          # /apps/miniconda3/envs/protenix
export PROTENIX_ROOT_DIR=/apps/Protenix
```

`PROTENIX_ROOT_DIR` is **mandatory** — see Gotchas. `predict.sh` sets it; anything else does not.

Local deviations from `requirements.txt` (intentional, do not "fix"):

| | requirements.txt | installed |
|---|---|---|
| torch | 2.7.1 | **2.9.0+cu128** — needed for `sm_120` (RTX PRO 6000 Blackwell, 96 GB) |
| protenix (pip metadata) | — | stale `1.0.4` in `protenix.egg-info`; `protenix --version` correctly reports 2.0.0 |

Search binaries are on `PATH` system-wide: `mmseqs`, `hmmsearch`, `jackhmmer`, `kalign`, `hhblits`.

## Commands

| Command | What it does |
|---|---|
| `./predict.sh <input_dir> <out_dir>` | **Primary workflow.** Batch-predicts every `*.json` in a dir, 8 jobs in parallel, skips dirs that already contain a `.cif` (resumable). |
| `protenix pred -i in.json -o out/` | Single prediction. Runs MSA/template prep first if the JSON lacks precomputed paths. |
| `protenix prep -i in.json --out_dir out/` | MSA + template + RNA-MSA search only, writes an enriched JSON. |
| `protenix msa` / `protenix mt` | MSA search / MSA+template search alone. |
| `protenix json` | Convert PDB/CIF → Protenix inference JSON. |
| `python runner/inference.py --model_name ... --input_json_path ...` | GPU-only path; **requires** MSA/template paths already in the JSON. Use for reproducible benchmarking. |
| `pytest tests/` | Unit tests (most need no GPU). **`pytest` is not in the env** — `pip install pytest` first; the system `pytest` at `~/.local/bin` can't import torch. |
| `pre-commit run --all-files` | flake8 + ufmt (black 22.12 + usort) + pydoclint + license-header insert. Already installed as a `.git/hooks/pre-commit` hook, so it also fires on every commit. |

`inference_demo.sh` is the canonical reference for every model/flag combination — read it before inventing a command line.

### Key inference flags

`-s/--seeds` `-c/--cycle` `-p/--step` `-e/--sample` `-d/--dtype` `-n/--model_name`,
plus `--use_msa`, `--use_template`, `--use_rna_msa`, `--use_default_params`,
`--trimul_kernel` / `--triatt_kernel` (`cuequivariance` is the default and fastest here),
`--msa_server_mode {protenix,colabfold}`.

`--use_default_params true` loads the per-model recommended `N_cycle`/`N_step` from `configs/configs_model_type.py`
and overrides `-c`/`-p`. `predict.sh` deliberately passes `false` and sets them explicitly.

## Models

Checkpoints live in `checkpoint/` (gitignored). Present locally:

| File | Params | Data cutoff | Notes |
|---|---|---|---|
| `protenix_base_20250630_v1.0.0.pt` | 368 M | 2025-06-30 | **Default for production runs** — `predict.sh` uses this. |
| `protenix_base_default_v1.0.0.pt` | 368 M | 2021-09-30 | AF3-comparable baseline; use for benchmarks against published numbers. |
| `protenix-v2.pt` | 464 M | 2021-09-30 | Opt-in only. Gains on antibody–antigen and ligand plausibility; **hard-fails on `n_token > 2560`**. Older cutoff than the 20250630 model, so not a blanket upgrade. |

Full catalogue (mini/tiny/ESM/ISM/constraint variants) in `docs/supported_models.md` and `configs/configs_model_type.py`.
Model name → architecture overrides are applied automatically from `--model_name`; `protenix-v2` for example switches
`c_z` 128 → 256. Model name → download URL lives in `protenix/web_service/dependency_url.py`.

## Data layout

All under `$PROTENIX_ROOT_DIR` (= repo root here). Every one of these is **gitignored** — large, machine-local:

```
checkpoint/         model .pt files
common/             components.cif (490 MB CCD), *.rdkit_mol.pkl, release_date_cache.json,
                    obsolete_to_successor.json, clusters-by-entity-40.txt, seq_to_pdb_index.json
mmcif/              template structures, auto-cached from EBI on demand
search_database/    89 GB of MSA/template FASTA DBs (pdb_seqres, rnacentral, rfam, nt_rna)
results/ test/ output/ release_data/    scratch
```

`scripts/database/download_protenix_data.sh` fetches `common/` and the databases.

## Architecture

```
protenix/
  model/         Protenix nn.Module, modules/ (pairformer, diffusion, confidence),
                 layer_norm/ + tri_attention/ + triangular/ = custom CUDA/Triton kernels
  data/          core/ (CCD, tokenizer), msa/, template/, inference/ (featurizers),
                 pipeline/ (training data), constraint/, esm/
  metrics/       lDDT, DockQ, PAE-derived scores
  web_service/   Colab/server request parsing, dependency_url.py
  tfg/           training-free guidance
runner/          inference.py (single job) · batch_inference.py (the `protenix` CLI, click) ·
                 train.py · msa_search.py · rna_msa_search.py · template_search.py · dumper.py · ema.py
configs/         configs_base.py (all defaults) · configs_data.py (paths) ·
                 configs_inference.py · configs_model_type.py (per-model overrides)
```

Config resolution in `runner/inference.py:run()` is a **two-pass merge**: parse args once to learn `model_name`,
deep-merge that model's overrides into the base config, then re-parse args so explicit CLI flags win.
Adding a model means touching `configs_model_type.py` + `dependency_url.py` + the guards in `runner/batch_inference.py`.

Output per job: `<out>/<name>/seed_<n>/predictions/<name>_sample_<i>.cif` plus
`<name>_summary_confidence_sample_<i>.json` (`plddt`, `ptm`, `iptm`, `gpde`, `has_clash`, `ranking_score`).

## Gotchas

- **`PROTENIX_ROOT_DIR` defaults to `$HOME`, not the repo.** Forget it and every run silently re-downloads
  `common/components.cif` (490 MB) into `~/common/`, plus checkpoints into `~/checkpoint/`. Downloads are slow
  (see next point) and a killed run leaves a truncated file that later runs will happily treat as a valid cache.
- **`protenix.tos-cn-beijing.volces.com` returns HTTP 403 from this network.** The auto-download in
  `runner/inference.py:download_from_url` therefore cannot fetch weights or `common/` data. Get checkpoints from a
  HuggingFace mirror instead and drop them in `checkpoint/<model_name>.pt`. Template mmCIFs are unaffected — they
  come from EBI and cache fine into `mmcif/`.
- First run of a session pays ~45 s parsing the CCD before the model even loads. Not a hang.
- `runner/inference.py` needs `PYTHONPATH=/apps/Protenix` (or run from the repo root); the `protenix` CLI does not.
- CCD/`components.cif` version matters for ligand chemistry. `common/` holds both the current file and a pinned
  `components.v20240608.cif` — don't swap them casually, predictions for CCD ligands can change.
- Template and RNA-MSA features are only supported by the `v1.0.0` models and `protenix-v2`;
  `runner/batch_inference.py` asserts on this.
- `pre-commit` auto-inserts the Apache license header into every new `.py`/`.sh`. Let it, rather than hand-writing one.

## Fork conventions

- The only substantive local addition is `predict.sh` (plus the `.gitignore` entries for the data dirs above).
  Keep the delta against upstream small so `git merge upstream/main` stays cheap.
- Sync with `git fetch upstream && git merge upstream/main` on `main`, then merge `main` into `dev`.
- Conventional-commit subjects (`feat:`, `fix:`, `chore:`, …). No AI/agent attribution trailers.
- CI (`.github/workflows/ci.yml`) only runs on `main`/PRs to `main` and is lint + `pytest` on Python 3.11.
