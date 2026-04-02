# 🏋️ Benchmark Task Descriptions

This document provides a detailed overview of the tasks used to evaluate LLM performance in the PCSS environment.

## 💬 Chat Tasks (Cognitive & Logic)
These tasks test the model's reasoning, coding, and formatting capabilities without tool access.

| ID | Category | Description |
| :--- | :--- | :--- |
| `chat_001` | **Logic & Constraints** | **Wolf, Goat, and Cabbage (Modified)**: A classic puzzle with an extra constraint: if the wolf stays alone for more than two turns, it runs away. Tests long-term planning and constraint satisfaction. |
| `chat_002` | **Code Architecture** | **Pydantic V2 Audit**: Analysis of a data model processing 1M records. Tests understanding of Pydantic performance patterns and Python memory efficiency. |
| `chat_003` | **Formatting** | **Complex JSON Serialization**: Generating a minified, single-line JSON representing a company structure with no newlines and UUIDs. Tests strict formatting adherence. |
| `chat_004` | **Math & Logic** | **Power of Two**: Calculating the sum of digits of 2^1000 and estimating its size. Tests mathematical intuition and algorithmic thinking. |
| `chat_005` | **Nuance** | **API Security Concepts**: Explaining the difference between *implicit* and *explicit* design in security. Tests conceptual clarity and technical writing. |

---

## 🤖 Agent Tasks (Tool Usage & Workflows)
These tasks test the model's ability to use the application's actual tools (Terminal, Python, Files, Search) to achieve goals.

| ID | Category | Success Criteria | Tools Used |
| :--- | :--- | :--- | :--- |
| `agent_001` | **Workflow** | **Cascade Research**: Find Fleming's discovery year, calculate decades to 2025 via Python, and save to `nobel_stats.txt`. | `search_web`, `run_python`, `write_file` |
| `agent_002` | **Computation** | **Stress Test**: Calculate 17^123, count occurrences of digit '7' in the string result. Tests high-precision math handling. | `run_python` |
| `agent_003` | **System** | **Self-Audit**: Read `CLAUDE.md`, count 'PCSS' occurrences manually, then verify using `grep` via terminal. Tests tool cross-verification. | `view_file`, `run_terminal` |
| `agent_004` | **Document** | **Doc Generation**: Create a formatted PDF/DOCX report `AI_Safety.pdf` with specific headers and bullet points. | `save_document` |
| `agent_005` | **Search** | **Multi-Hop Fact Check**: Identify the Director of PCSS and trace their PhD degree source. Tests data grounding and link following. | `search_web` |

---
*Note: Results of these tests are tracked in [`BENCHMARK_RESULTS.md`](./BENCHMARK_RESULTS.md).*
