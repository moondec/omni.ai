# PCSS LLM Client

<img src="resources/logo.png" align="right" width="240" />

A Python desktop application (GUI) for interacting with the PCSS LLM Service, built with **PySide6 (Qt)** and **LangChain**.

> Tested on macOS. Need more tools and tests. But current version is promising.

## ✨ Key Features

### 1. 💬 Chat Mode
-   **Conversation History**: All chats are saved locally to an SQLite database (`conversations.db`).
-   **Model Selection**: Dynamically fetches models from PCSS (e.g., `bielik_11b`, `DeepSeek-V3.1-vLLM-2`).
-   **Import/Export**: Save and load specific conversations to JSON files.
-   **Markdown Support**: Full rendering of headings, code blocks, and lists.

### 2. 🤖 Agent Mode (Autonomous)
The application features a powerful Agent capable of performing complex, multi-step tasks.

**File Management**
-   `list_directory`, `write_file`, `copy_file`, `move_file`, `delete_file`
-   `view_file` — read file content with **1-indexed line numbers** (auto-truncates to protect context limits).
-   `replace_file_content` — **precision line-based editing**: surgically targets specific code blocks via start/end line integers instead of brittle string matching.
-   `search_files` — cross-file pattern/string search across the workspace

**Code & Data Execution**
-   `run_terminal` — sandboxed shell execution (e.g., `python app.py`) with strict workspace constraints and robust timeout / SIGKILL logic.
-   `run_python` — execute Python code snippets for calculations, data processing, and logic testing

**Internet & Research**
-   `search_web` — DuckDuckGo general search
-   `search_news` — DuckDuckGo latest news
-   `visit_page` — fetch and extract full article text from a URL (up to 15,000 chars)
-   `deep_research` — **automated research pipeline**: runs multiple searches, visits top sources, summarizes each with AI, and returns a structured report

**Browser Automation (MCP)**
-   `playwright_*` — 33+ tools for headless browser control (navigate, click, type, screenshot) using **Model Context Protocol**

**Document Processing**
-   `read_pdf`, `read_docx`, `save_document`, `convert_document` — read and generate PDF/DOCX files
-   `ocr_image` — extract text from images/scans (Nanonets OCR)
-   `generate_chart` — generate charts and visualizations from data

**System Architecture**
-   **Profiles**: YAML-based agent personas (researcher, coder, writer…) enforcing strict ReAct paradigms.
-   **Persistent Memory**: Agents utilize `.agent_context.md` auto-briefing upon load/restart, carrying over project knowledge across sessions.
-   **Workspace Security**: Agent execution (Terminal & Files) is strictly confined to a configured root directory.
-   **Fine-Adjustment (Few-Shot Tuning)**: The Agent automatically dynamicly fetches high-rated (Thumbs Up) previous interactions from the local database and uses them as **few-shot examples**. This allows the Agent to "learn" your preferred style and tool usage patterns without requiring actual model training.

### 3. 🔒 Security
-   **Secure Storage**: API Keys are stored in the system Keyring (macOS Keychain, Windows Credential Locker), never in plain text.
-   **Local Data**: All history and settings are stored locally.
-   **Documentation**: See [MODEL_GUIDE.md](MODEL_GUIDE.md) and [TOOLS_GUIDE.md](TOOLS_GUIDE.md).

### 4. 💬 Chat vs. 🤖 Agent (Important!)

| Feature | **Chat Tab** | **Agent Mode Tab** |
| :--- | :--- | :--- |
| **Primary Use** | Conversation, Q&A | **Executing Tasks**, Research, Coding |
| **Tools Access** | ❌ No Tools | ✅ Full Toolbox |
| **Internet** | ❌ Offline | ✅ **Online** (DuckDuckGo, Deep Research) |
| **File System** | ❌ No access | ✅ Read, Write, Edit, Search |
| **Python Execution** | ❌ | ✅ `run_python` |

> [!IMPORTANT]
> If you want the model to **search the web**, **read files**, or **run code**, you MUST use the **Agent Mode** tab.

## 🛠️ Installation

### Prerequisites
-   **Anaconda** or **Miniconda** installed.
-   Python **3.10+**
-   **Node.js / npm** — required for the Playwright MCP server (`npx`).
-   **Pandoc** >= 3.0 ([Download](https://github.com/jgm/pandoc/releases)) — required for document conversion.

### Setup (Conda - Recommended for macOS/Linux)

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/moondec/PCSS-frontend-LLM.git
    cd Bielik
    ```

2.  **Create the Conda Environment**
    ```bash
    conda env create -f environment.yml
    conda activate bielik
    ```

    *Or manually (includes all new dependencies):*
    ```bash
    conda create -n bielik python=3.11 -y
    conda activate bielik
    conda install -c conda-forge pyside6 openai keyring markdown \
        langchain langchain-openai langchain-community \
        pypdf python-docx openpyxl pypandoc weasyprint \
        duckduckgo-search requests beautifulsoup4 \
        matplotlib-base pyyaml pandas numpy pygments pydantic -y
    pip install readability-lxml mcp langchain-mcp-adapters pdfplumber
    ```

    > [!NOTE]
    > `readability-lxml` is a `pip`-only package and is **required** for the `visit_page` and `deep_research` tools to extract article content from web pages. It is already included in `environment.yml`.

### Setup Alternative (venv + pip - Recommended for Windows)

If you encounter DLL/PySide6 installation issues via Conda on Windows, it is highly recommended to use the standard Python `venv` with `pip`:

1.  **Clone the Repository**
    ```cmd
    git clone https://github.com/moondec/PCSS-frontend-LLM.git
    cd Bielik
    ```

2.  **Create and activate the virtual environment**
    ```cmd
    python -m venv venv
    venv\Scripts\activate
    ```

3.  **Install requirements**
    ```cmd
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

1.  **API Key**: On first launch, enter your PCSS Cloud API Token (corresponds to your active Grant). See [MODEL_GUIDE.md](MODEL_GUIDE.md) for more information.
2.  **Workspace**: In **Settings**, select the directory where the Agent is allowed to operate (Default: `~/Documents/Bielik_Workspace`).

## ▶️ Usage

If using Conda:
```bash
conda activate bielik
python pcss_llm_app/main.py
```

If using venv on Windows:
```cmd
venv\Scripts\activate
python pcss_llm_app\main.py
```

## ⚠️ Conda update

# Switch to base environment

conda activate base

# Update conda to the latest version

conda update -n base conda

## Environment update

First get newest version of the code:

```bash
git pull
```

Then update environment (Conda):

```bash
# Update environment based on the YAML file
conda env update --file environment.yml --prune
```

Or if using venv:
```cmd
pip install -r requirements.txt
```

### Tips
-   **Chat**: `Shift+Enter` for new lines, `Enter` to send.
-   **Agent**: Go to **Agent Mode** → **Create Assistant** to initialize the engine. Then type requests like:
    -   *"Przeprowadź deep research na temat AI w Polsce i zapisz raport do raport.md"*
    -   *"Przeczytaj report.pdf i stwórz podsumowanie summary.txt"*
    -   *"Napisz skrypt Python i uruchom go, aby sprawdzić dane"*

## 🏗️ Technology Stack

| Layer | Technology |
| :--- | :--- |
| **GUI** | PySide6 (Qt6) |
| **LLM Engine** | LangChain + LangGraph |
| **API** | OpenAI Compatible (PCSS HPC) |
| **Database** | SQLite |
| **Web Search** | DuckDuckGo (`ddgs`) |
| **Browser Auto (MCP)** | `mcp`, `playwright-mcp-server` via `npx` |
| **Web Scraping** | `requests`, `beautifulsoup4`, `readability-lxml` |
| **Documents** | `pypdf`, `python-docx`, `pypandoc`, `weasyprint` |
| **Visualization** | `matplotlib` |
