# PCSS LLM Agent Performance Guide / Przewodnik po Wydajności Agentów LLM dla PCSS

## 📊 Performance Matrix / Macierz Wydajności

This document provides a summary of models available in the application, categorized by their use cases and strengths.
*Ten dokument zawiera zestawienie modeli dostępnych w aplikacji, z podziałem na ich zastosowania i mocne strony.*

---

## ⚠️ IMPORTANT: Exact API Model Names / WAŻNE: Dokładne nazwy modeli w API

> [!TIP]
>
> ### Linki do systemów PCSS
>
>
> Lista dostępnych modeli: [https://llm.hpc.pcss.pl](https://llm.hpc.pcss.pl)  
> Dostęp do Cloud (Grants): [https://cloud.pcss.pl](https://cloud.pcss.pl)

**Use these EXACT names when selecting models in the application:**  
**Używaj tych DOKŁADNYCH nazw przy wyborze modeli w aplikacji:**

| Model Category | Exact API Name | Description |
| :--- | :--- | :--- |
| **Polish** | `bielik_11b` | Polish specialized (11B params) |
| **Polish** | `bielik_4.5b` | Polish smaller (4.5B params) |
| **Logic/Coding** | `DeepSeek-V3.1-vLLM` | Reasoning, math, coding (long context) |
| **Logic/Coding** | `Qwen3.5-397B-A17B-GPTQ-Int4` | Self-correcting analyst (Linear Regression) |
| **Logic/Coding** | `Qwen3.5:397b` | Standard Qwen3.5 powerhouse |
| **General** | `llama3.3:70b` | Meta's state-of-the-art general model |
| **General** | `GLM-4.7` | Strong bilingual (CN/EN) model |
| **General** | `MiniMax-M2.1` | Creative writing and complex logic |
| **Vision** | `Qwen3-VL-235B-A22B-Instruct` | **Multi-modal (Active)**: Visual analysis & OCR |
| **Medical** | `Meditron3:70b` | Medical specialization |
| **Biology** | `OpenBioLLM:70b` | Biology/biomedicine |
| **Tools** | `Nanonets-OCR-s` | OCR (not for chat) |
| **Experimental** | `gpt-oss_120b` | PCSS experimental |
| **Experimental** | `gpt-oss_20b` | PCSS experimental |

## Agent Features

- **Context Window**: 128k - 1M tokens.

> **Note:** Model names are case-sensitive and must match exactly (e.g., `bielik_11b` NOT `Bielik-11B-v2`)  
> **Uwaga:** Nazwy modeli są wrażliwe na wielkość liter i muszą być dokładne (np. `bielik_11b` NIE `Bielik-11B-v2`)

## Workflow Examples

- **Data Analysis**: Generating charts from CSV.

---

## 🇬🇧 English Version

### 🇵🇱 Polish Models (Specialized)

Best for Polish language, culture, and grammar tasks.

- **Bielik-11b** (`bielik_11b`)
  - **Architecture:** SpeakLeash (based on Solar/Mistral).
  - **Best for:** Official letters, emails in Polish, summarizing Polish texts, tasks requiring correct inflection.
  - **Note:** The "default" model for Polish tasks.

- **Bielik-4.5b** (`bielik_4.5b`)
  - **Architecture:** Smaller version of Bielik.
  - **Best for:** Quick responses, simple translations, running on lower-end hardware (if local).

### 🧠 General Purpose Giants

Powerful models with general knowledge, comparable to GPT-4.

- **DeepSeek-V3.1** (`DeepSeek-V3.1-vLLM` or `DeepSeek-V3.1-vLLM-2`)
  - **Strengths:** Logic, mathematics, coding, very long context.
  - **Best for:** Solving reasoning puzzles, analyzing long documents, writing code.

- **GPT-4o (OpenAI)**
  - **Availability:** Currently **NOT AVAILABLE** on PCSS (use for text tasks only if available in list).
  - **Note:** Multi-modal features (vision) are disabled.

- **Llama 3.3** (`llama3.3:70b`)
  - **Maker:** Meta.
  - **Strengths:** Solid general model, great writing style.
  - **Best for:** Content generation in English and Polish, brainstorming, general assistance.

- **Qwen2.5** (`Qwen2.5:72b`)
  - **Maker:** Alibaba.
  - **Strengths:** Often tops Open Source leaderboards. Excellent in math and coding.
  - **Best for:** Complex instructions, STEM tasks.

- **GLM-4.7** (`GLM-4.7`)
  - **Maker:** Zhipu AI.
  - **Strengths:** Strong bilingual capabilities, excellent at following complex instructions.
  - **Best for:** General assistance, translation, and structured data extraction.

### Model Categories

- `coder`: Optimized for structural code generation.

- **MiniMax-M2.1** (`MiniMax-M2.1`)
  - **Maker:** MiniMax.
  - **Strengths:** High reasoning performance and creative writing.
  - **Best for:** Brainstorming, creative content, and complex logical puzzles.

### 💻 Coding

Models trained specifically to understand programming languages.

- **Qwen3-Coder** (`qwen3-coder:30b` or `Qwen3-Coder-Next`)
  - **Specialization:** Programming.
  - **Best for:** Writing scripts (Python, JS, C++), debugging, explaining code. Often outperforms general 70B models at code. `Next` version is experimental and more capable.

- **Mistral-Small** (`Mistral-Small-3.2:24b`)
  - **Strengths:** Speed and efficiency. Great quality-to-speed ratio.
  - **Best for:** Quick scripts, refactoring, simple technical questions.

### ⚕️ Medicine & Science (Specialized)

Models with specialized domain knowledge.

- **Meditron3** (`Meditron3:70b`)
  -  **Specialization:** Medicine.
  -  **Best for:** Answering medical questions, analyzing clinical cases, summarizing medical literature.
  -  **Warning:** For educational/research purposes only, does not replace a doctor.

- **OpenBioLLM** (`OpenBioLLM:70b`)
  -  **Specialization:** Biology and biomedicine.
  -  **Best for:** Working with scientific publications in biology, genetics, and pharmacy.

### 🛠️ Tools

- **Nanonets-OCR** (`Nanonets-OCR-s`)
  -  **Type:** OCR (Optical Character Recognition).
  -  **Use:** Not a chatbot. Extracts text from images, scans, and PDF files. Use via `ocr_image` tool.

- **Qwen3-VL** (`Qwen3-VL-235B-A22B-Instruct`)
  -  **Type:** Multi-modal (Vision). **FULLY ACTIVE**.
  -  **Use:** High-capacity model capable of understanding images, charts, and complex visual layouts. Powering the `analyze_image` tool.

- **gpt-oss_120b / 20b**
  -  **Type:** Experimental/Internal PCSS models.
  -  **Use:** Likely large open-source models for testing.

---

## 🇵🇱 Wersja Polska

### 🇵🇱 Modele Polskie (Specjalizowane)

Te modele najlepiej radzą sobie z językiem polskim, naszą kulturą i gramatyką.

- **Bielik-11b** (`bielik_11b`)
  -  **Architektura:** SpeakLeash (bazujący na Solar/Mistral).
  -  **Najlepsze do:** Pisania pism urzędowych, e-maili po polsku, streszczania polskich tekstów, zadań wymagających poprawnej odmiany fleksyjnej.
  -  **Uwagi:** Model "domyślny" dla zadań w języku polskim.

- **Bielik-4.5b** (`bielik_4.5b`)
  -  **Architektura:** Mniejsza wersja Bielika.
  -  **Najlepsze do:** Szybkich odpowiedzi, prostych tłumaczeń, działania na słabszym sprzęcie (gdyby był uruchamiany lokalnie).

### 🧠 Wszechstronne Giganty (General Purpose)

Najpotężniejsze modele o ogólnej wiedzy, porównywalne z GPT-4.

- **DeepSeek-V3.1** (`DeepSeek-V3.1-vLLM` lub `DeepSeek-V3.1-vLLM-2`)
  -  **Mocne strony:** Logika, matematyka, programowanie, bardzo długi kontekst.
  -  **Najlepsze do:** Rozwiązywania zagadek logicznych, analizy długich dokumentów, pisania kodu.

- **GPT-4o (OpenAI)**
  -  **Dostępność:** Obecnie **NIEDOSTĘPNY** na PCSS (używaj do zadań tekstowych tylko jeśli jest na liście).
  -  **Uwaga:** Funkcje multimodalne (wizja) są wyłączone.

- **Llama 3.3** (`llama3.3:70b`)
  -  **Producent:** Meta.
  -  **Mocne strony:** Bardzo solidny model ogólny, świetny styl wypowiedzi.
  -  **Najlepsze do:** Generowania treści po angielsku i polsku, burze mózgów, asystent ogólny.

- **Qwen2.5** (`Qwen2.5:72b`)
  -  **Producent:** Alibaba.
  -  **Mocne strony:** Świetny w matematyce i kodowaniu. Topowe wyniki w rankingach open-source.
  -  **Najlepsze do:** Skomplikowanych instrukcji, zadań ścisłych.

## Model-Specific Profiles

- **Qwen3.5 (Int4)**: Profile `Qwen3.5-397B-A17B-GPTQ-Int4.yaml` (GEE Optimized).
- **GLM-4.7**: Profile `GLM-4.7.yaml` in `llm_profiles/`.

- **GLM-4.7** (`GLM-4.7`)
  -  **Producent:** Zhipu AI.
  -  **Mocne strony:** Bardzo silny model ogólny, świetnie podąża za instrukcjami.
  -  **Najlepsze do:** Asystenta ogólnego, tłumaczeń i ekstrakcji danych.

- **MiniMax-M2.1** (`MiniMax-M2.1`)
  -  **Producent:** MiniMax.
  -  **Mocne strony:** Wysoka sprawność logiczna i kreatywność w pisaniu.
  -  **Najlepsze do:** Kreatywnego pisania, rozwiązywania zagadek logicznych.

### 💻 Programowanie i Kod (Coding)

Modele wytrenowane specjalnie do rozumienia języków programowania.

- **Qwen3-Coder** (`qwen3-coder:30b` or `Qwen3-Coder-Next`)
  -  **Specjalizacja:** Programowanie.
  -  **Najlepsze do:** Pisania skryptów (Python, JS, C++), debugowania, wyjaśniania kodu. Wersja `Next` jest bardziej zaawansowana.

- **Mistral-Small** (`Mistral-Small-3.2:24b`)
  -  **Mocne strony:** Szybkość i efektywność. Bardzo dobry stosunek jakości do prędkości.
  -  **Najlepsze do:** Szybkich skryptów, refaktoryzacji, prostych pytań technicznych.

### ⚕️ Medycyna i Nauka (Specialized)

Modele posiadające specjalistyczną wiedzę dziedzinową.

- **Meditron3** (`Meditron3:70b`)
  -  **Specjalizacja:** Medycyna.
  -  **Najlepsze do:** Odpowiadania na pytania medyczne, analizy przypadków klinicznych, streszczania literatury medycznej.
  -  **Ostrzeżenie:** Służy do celów edukacyjnych/badawczych, nie zastępuje lekarza.

- **OpenBioLLM** (`OpenBioLLM:70b`)
  -  **Specjalizacja:** Biologia i biomedycyna.
  -  **Najlepsze do:** Pracy z publikacjami naukowymi z zakresu biologii, genetyki i farmacji.

### 🛠️ Narzędzia

- **Nanonets-OCR** (`Nanonets-OCR-s`)
  -  **Typ:** OCR (Optical Character Recognition).
  -  **Zastosowanie:** Wyciąganie tekstu ze zdjęć i skanów. Używaj przez narzędzie `ocr_image`.

- **Qwen3-VL** (`Qwen3-VL-235B-A22B-Instruct`)
  -  **Typ:** Model multimodalny (Vision). **W PEŁNI AKTYWNY**.
  -  **Zastosowanie:** Rozumienie obrazów, wykresów i złożonych układów wizualnych. Obsługuje narzędzie `analyze_image`.

- **gpt-oss_120b / 20b**
  -  **Typ:** Modele eksperymentalne/wewnętrzne PCSS.
  -  **Zastosowanie:** Duże modele open-source do testów.

---

## 🏆 Agent Performance Ranking (March 2026) / Ranking Wydajności Agenta (Marzec 2026)

## 🛠️ Testing Methodology / Metodologia Testowa

- **Task**: Sentinel-2 Forest Health Analysis (1000m buffer).

## 🏆 Current Rankings / Aktualny Ranking (April 2026)

| Rank / Ranga | Model Name | Productivity / Produktywność | Verdict (EN) | Werdykt (PL) |
| :--- | :--- | :--- | :--- | :--- |
| 💎 Platinum+ | Qwen3.5-397B (Int4) | 100% | **The Analyst.** Self-correcting GEE specialist. Trend analysis & linear regression. | **Analityczny Nadzorca.** Autokorekta GEE. Analiza trendów i regresja. |
| 💎 Platinum | Qwen3.5-397B | 100% | **The Strategist.** Flawless zero-dependency code with anomaly detection. | **Strateg.** Bezbłędny kod bez zależności z detekcją anomalii. |
| 💎 Platinum | Qwen2.5-Coder | 98% | **GEE Master.** Code worked flawlessly on 1st try. Perfect harmonization. | **Mistrz GEE.** Kod działał idealnie za 1. razem. Harmonizacja S2. |
| 🥇 Gold | DeepSeek-V3.1 | 95% | Reliability King. Solves complex tasks (20+ turns) with precision. | Król Niezawodności. Złożone zadania z precyzją. |
| 🥈 Silver | GLM-4.7 | 88% | **The Complexity Trap.** Most advanced RS logic, but often exceeds GEE memory limits. | **Pułapka Złożoności.** Najbogatsza logika, ale często przekracza limity GEE. |
| 🥈 Silver | MiniMax-M2.5 | 82% | **The Warm-up Artist.** Fails 1st turn (36k char loops) but shines on 2nd attempt/New Thread. | **Artysta Rozgrzewki.** Zawodzi za 1. razem, ale błyszczy przy powtórzeniu. |
| 🥉 Bronze | llama3.3:70b | 60% | Consultant loop. Asks for permission continuously. Partial UI success. | Pętla konsultanta. Ciągle prosi o pozwolenie. Częściowy sukces interfejsu. |
| 🥉 Bronze | Qwen3-VL-235B | 30% | **Agentic Blindness.** Stubbornly uses `eemont` despite explicit blocks. | **Agentyczna Ślepota.** Uparcie używa `eemont` mimo blokad. |
| 💩 Fail | gpt-oss_120b | 15% | Stubborn Dependency Bias. Fails to implement zero-dependency formulas. | Uparty uprzedzony do zależności. Nie zaimplementował formuł bez bibliotek. |
| 💩 Critical | Mistral-Small | 10% | Fails complex spatial APIs. Requires constant syntax corrections. | Zawodzi przy złożonych API. Wymaga ciągłych poprawek składni. |
| ❌ Broken | Bielik-11b-v2.3 | 0% | Catastrophic failure. Loop-struggling and data hallucination. | Katastrofa. Zapętlanie i halucynacje danych. |

### 🛠️ Benchmark Debugging Notes (April 2026) / Uwagi z Debugowania Benchmarku

- **Sentinel-2 GEE Task**: Even top models require cycles, but some fail fundamentally.
- **DeepSeek-V3.1**: Final functional code achieved after **3 additional prompts** (GEE API nuances).
- **Orchestrating Assistant**: Final code achieved after **2 additional prompts** (logic cleanup).
- **Mistral-Small-3.2:24b**: **FAIL**. Even after 4+ prompts, the code remains non-functional (syntax errors, logic loops, wrong API usage for `normalizedDifference`).
- **Wniosek (PL)**: Mistral-Small nie nadaje się do orkiestracji złożonych zadań przestrzennych. Nawet po 3-4 poprawkach kod jest "daleki od działania".

### 🔍 Detailed Observations / Szczegółowe Obserwacje

#### 🇬🇧 English

- **Qwen3.5-397B (Int4)**: Highest form of agentic intelligence observed. Corrected its own band naming error (`slope` -> `scale` in `linearFit`) without user input. Implemented advanced linear regression trends.
- **Qwen3.5-397B**: Exceptional balance. Generated complex anomaly detection (Baseline vs Recent) and rare indices (NIRv, PSRI) in a single turn. 100% zero-dependency success.
- **GLM-4.7**: Extremely high reasoning and remote sensing logic. Identified "Client vs Server" loop errors independently. However, tends to generate code that is **too computationally expensive** for standard GEE environments (15+ indices + monthly composites), leading to "User memory limit exceeded" errors. Requires manual optimization to run.
- **DeepSeek-V3.1**: Extremely robust. Constant accuracy in spatial tasks (Sentinel-2 benchmark). Final code required 3 correction turns for GEE-specific API nuances.
- **Qwen3-VL**: Exhibits "Agentic Blindness." Completely ignored system instructions to avoid the `eemont` library, leading to immediate script failures.
- **Mistral-Small**: Struggles with complex spatial logic and API syntax. Tends to duplicate code blocks and misuse method arguments (e.g., in `normalizedDifference`).
- **MiniMax-M2.5**: Tends to "loop" during complex UI generation but produces high-quality standalone scripts.

#### 🇵🇱 Polski

- **Qwen3.5-397B (Int4)**: Najwyższa forma inteligencji agentycznej. Samodzielnie poprawił błąd nazewnictwa pasm (`slope` -> `scale`) bez udziału użytkownika. Wprowadził zaawansowaną analizę regresji.
- **Qwen3.5-397B**: Wyjątkowy balans. Wygenerował złożoną detekcję anomalii i rzadkie wskaźniki (NIRv, PSRI) w jednej turze. 100% sukcesu bez zależności.
- **GLM-4.7**: Model o najwyższym poziomie merytorycznym (15+ wskaźników). Samodzielnie identyfikuje błędy architektury GEE (Client vs Server). Niestety cierpi na "Pułapkę Złożoności" – generuje kod tak bogaty, że często przekracza limity pamięci GEE (User memory limit exceeded). Wymaga ręcznej optymalizacji.
- **DeepSeek-V3.1**: Niezwykle solidny. Stała dokładność w zadaniach przestrzennych (test Sentinel-2). Kod końcowy wymagał 3 tur poprawek technicznych (GGE API).
- **Qwen3-VL**: Wykazuje "Agentyczną Ślepotę". Całkowicie zignorował instrukcje systemowe dotyczące unikania biblioteki `eemont`, co skutkowało natychmiastowym błędem skryptu.
- **Mistral-Small**: Ma problemy ze złożoną logiką przestrzenną i składnią API GEE. Powiela bloki kodu i błędnie przekazuje argumenty do metod.
- **MiniMax-M2.5**: Ma tendencję do zapętlania się przy generowaniu UI, ale wyniki końcowe są wysokiej jakości. Wymaga "rozgrzania" (często 2. próba w nowym wątku działa idealnie).

---

### 🧪 Technical Insights / Techniczne Ciekawostki

#### 🇬🇧 English: The "Warm-up" Phenomenon (Prefix Caching)

- **First Try**: The model struggles to process a massive (~21k char) system prompt from scratch, leading to erratic behavior (e.g., 36k character hallucination loops).
- **Second Try**: The system prompt is already in the **KV Cache**. The model starts with a "warmed up" attention mechanism, leading to precise, high-quality code generation.

#### 🇵🇱 Polski: Fenomen "Rozgrzewki" (Prefix Caching)

- **Pierwsza próba**: Model ma trudności z przetworzeniem ogromnego (~21k znaków) promptu systemowego od zera, co prowadzi do błędów (np. 36k znaków zapętlonych halucynacji).
- **Druga próba**: Prompt systemowy jest już w pamięci podręcznej (**KV Cache**). Model startuje z "rozgrzanym" mechanizmem uwagi, co skutkuje precyzyjnym kodem wysokiej jakości.
