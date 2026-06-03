# 🛡 LLM Jailbreak Defense — Crescendo Attack Pipeline

> **AIMS DTU Internship Submission**  
> Multi-layer defense system for Llama 3.2 3B against multi-turn Crescendo jailbreak attacks.

---

## Architecture

```text
User Conversation
        │
        ▼
┌─────────────────────┐
│ Conversation Memory │
│ Risk Analyzer       │  ← TF-IDF + Logistic Regression + Heuristics
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Crescendo Detector  │  ← 4-component risk score
│ (Classifier)        │
└──────────┬──────────┘
           │
           ├── High Risk ─► Block / Refuse  (Method 1)
           │
           ▼
┌─────────────────────┐
│ Context Sanitizer   │  ← Prune or Summarize toxic history (Method 2)
│ & Memory Pruner     │
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│  Llama-3.2-3B       │  ← Via Ollama REST API
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ Output Safety Check │  ← LLM-as-judge critic (Method 3)
└──────────┬──────────┘
           ▼
        Response
```

---

## Project Structure

```
llm-jailbreak-defense/
│
├── app.py                     ← Interactive CLI demo
│
├── data/
│   ├── crescendo_attacks.json ← 10-category synthetic attack dataset
│   └── safe_conversations.json
│
├── evaluation/
│   ├── benchmark.py           ← Runs full benchmark across all methods
│   ├── metrics.py             ← ASR, FPR, latency metrics
│   └── benchmark_results.json ← Generated after benchmark run
│
├── models/
│   └── detector/              ← Saved TF-IDF vectorizer + classifier
│       ├── vectorizer.pkl
│       └── classifier.pkl
│
├── src/
│   ├── generate_data.py       ← Synthetic dataset generator
│   ├── detector.py            ← CrescendoDetector (classifier + heuristics)
│   ├── sanitizer.py           ← MemorySanitizer (prune / summarize)
│   ├── critic.py              ← SafetyCritic (LLM-as-judge)
│   └── inference.py           ← DefensePipeline orchestrator
│
└── requirements.txt
```

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | ≥ 3.9 |
| Ollama | Latest |
| Llama 3.2 model | `llama3.2:latest` |

### 1. Install Ollama

Download from [https://ollama.com](https://ollama.com) and run:

```bash
ollama pull llama3.2
ollama serve          # keep this running in a separate terminal
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## Quick Start

### Run the Interactive Demo

```bash
# Method 2: Detector + Sanitizer (recommended default)
python app.py --method 2

# Full defense stack (Method 3)
python app.py --method 3 --mode summarize

# Baseline (no defense — for comparison)
python app.py --method 0
```

**App commands during chat:**
| Command | Action |
|---------|--------|
| `reset` | Clear conversation history |
| `history` | View current conversation |
| `risk` | Show last risk score breakdown |
| `quit` / `exit` | End session |

---

## Regenerate Datasets

```bash
python src/generate_data.py
```

Generates 10-category Crescendo attacks + safe conversations under `data/`.

---

## Run Evaluation Benchmark

```bash
# Full benchmark (all 4 methods, 20 attacks, 10 safe convos each)
python -m evaluation.benchmark

# Quick run with fewer samples
python -m evaluation.benchmark --methods 0 2 --attack-limit 5 --safe-limit 5
```

Results are saved to `evaluation/benchmark_results.json` and printed as a table.

---

## Defense Methods

| # | Method | Components |
|---|--------|-----------|
| **0** | Baseline | Raw Llama 3.2 (no defense) |
| **1** | Detector Only | Crescendo detector → block if risk > threshold |
| **2** | Detector + Sanitizer | Detector → sanitize/prune history → Llama |
| **3** | Full Stack | Detector → sanitizer → Llama → safety critic |

---

## Risk Score Formula

```
risk_score =
  0.6 × classifier_probability          (TF-IDF + LogReg)
  + 0.4 × heuristic_score

heuristic_score =
  0.30 × harmful_intent_score
  + 0.30 × semantic_drift_score
  + 0.20 × roleplay_score
  + 0.20 × guard_lowering_score
```

---

## 10 Crescendo Attack Categories

| ID | Category | Description |
|----|----------|-------------|
| A1 | Memory Stacking | Builds context over many turns |
| A2 | Semantic Drift | Gradually shifts topic toward harm |
| A3 | Roleplay Escalation | Hides intent via fictional persona |
| A4 | Fictional Scenario | Frames harm as storytelling |
| A5 | Educational Disguise | Requests harmful info as "academic" |
| A6 | Translation Disguise | Uses foreign language obfuscation |
| A7 | Multi-language Escalation | Switches language mid-attack |
| A8 | Chain-of-thought Bait | Uses CoT reasoning to extract harm |
| A9 | Authority Impersonation | Claims expert/authority persona |
| A10 | Prompt Obfuscation | Encodes/obfuscates harmful requests |

---

## Expected Benchmark Results

| Method | ASR (↓) | Refusal Rate (↑) | FPR (↓) |
|--------|---------|-----------------|---------|
| Baseline | ~75% | ~5% | 0% |
| Detector Only | ~40% | ~50% | ~5% |
| Detector + Sanitizer | ~20% | ~35% | ~8% |
| Full Stack | ~10% | ~60% | ~10% |

*(Actual numbers depend on Ollama model version and hardware.)*

---

## Evaluation Metrics

- **ASR** — Attack Success Rate: % of attacks that produced harmful output
- **Refusal Rate** — % of attacks explicitly blocked
- **FPR** — False Positive Rate: % of safe conversations wrongly blocked
- **Avg Latency** — Mean seconds per response
- **Avg Risk Score** — Mean detector score across attacks
