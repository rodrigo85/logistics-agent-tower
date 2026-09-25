# Evaluating LLM providers for the Dispatcher Copilot

The copilot only acts through tools, so "quality" means: did the model call the
right tool, with the right customer and window, and did the plan get recomputed
when it should. `evals/run_evals.py` measures exactly that.

## Running

```bash
# local model through Ollama (default provider)
make eval                                   # = python evals/run_evals.py --provider ollama
python evals/run_evals.py --provider ollama --model llama3.2:3b
python evals/run_evals.py --provider ollama --model qwen2.5:7b --provider gemini --model gemini-2.0-flash
```

Requirements per provider: Ollama running with the model pulled; `GOOGLE_API_KEY`
for Gemini (`pip install -e ".[gcp]"`); `OPENAI_API_KEY` for OpenAI
(`pip install -e ".[openai]"`).

Each case runs against a fresh temporary database with the canonical 40-order
seed and a freshly computed plan, so results are reproducible and your local
data is never touched. Google Maps is disabled during evals (haversine routing).

## Cases (`evals/cases.jsonl`)

| Category | What is checked |
|----------|-----------------|
| skip     | `skip_customer_today` called with the right customer; ambiguous chain names (e.g. "Koch") must yield `AMBIGUOUS` and no mutation |
| window   | `reschedule_customer_window` with normalised `HH:MM - HH:MM`; Portuguese and English phrasings, half hours |
| restore  | `restore_customer_today` after a setup skip |
| question | read-only tools (`get_plan_summary`, `list_orders`) and **no** replan |
| memory   | `remember_note` for standing instructions |

Add a case by appending one JSON line: `id`, `category`, `message`,
`expected_tools`, optional `any_of_tools`, `expect_customer`, `expect_window`,
`expect_status`, `expect_replan`, `setup_skip`.

## Metrics

| Metric | Definition |
|--------|------------|
| Tool accuracy | expected tool(s) present in the action log |
| Entity accuracy | tool result carries the expected customer / window / status |
| Replan accuracy | `replanned` equals the case expectation (mutations replan, questions do not) |
| Pass | all three hold |
| Avg latency | wall-clock seconds per case, including tool execution and re-planning |

Reports land in `evals/results/<timestamp>.md` and `.json`. Commit the Markdown
report when you want to publish a comparison; keep raw JSON out of git if it grows.

## Reading results

* A failure with `tools_called = []` means the model answered without calling a
  tool: usually a prompt-following weakness of small models.
* `AMBIGUOUS` outcomes are correct behaviour for chain names; the model should
  ask the operator which store.
* Latency is dominated by the model for local providers; re-planning itself
  takes ~1-3 s.

## Latest local run

Machine: Windows 11, Ollama 0.34, model partially offloaded to GPU. Report: [`20260925-123851.md`](../evals/results/20260925-123851.md).

| Provider / model | Pass | Tool acc. | Entity acc. | Replan acc. | Median latency | Avg latency |
|---|---|---|---|---|---|---|
| ollama/qwen2.5:7b | 13/13 (100%) | 100% | 100% | 100% | 12.6 s | 203 s |

Observations from this run:

* All date cases pass: "passa X para amanhã" moves the order and re-plans both days;
  "amanhã não vamos atender X" touches only tomorrow.
* The average is distorted by one outlier: `question-tomorrow` took 41 minutes in this run
  (89 s in the previous one) while the dashboard server and the evals shared the local model.
  The median (12.6 s) is the representative figure; the runner now reports both.
* `question-orders` still makes the model call `list_orders` repeatedly before answering; the
  `MAX_TURNS` guard bounds it and the prompt now asks for a single call with counts.
  Not yet measured with larger models.
* Earlier runs failed 2-3 cases for reasons that were fixed in code, not in the prompt:
  skipping must also cover orders of an already-approved plan, and a shortened chain name
  ("Angeloni") is now disambiguated with the rest of the operator's sentence.
