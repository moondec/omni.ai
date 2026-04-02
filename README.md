# PCSS LLM Client

<img src="resources/logo.png" align="right" width="240" />

A Python desktop application (GUI) for interacting with the PCSS LLM Service, built with **PySide6 (Qt)** and **LangChain**.

> Tested on macOS. Need more tools and tests. But current version is promising.

## ✨ Key Features

### 1. 💬 Chat Mode
-   **Conversation History**: All chats are saved locally to an SQLite database (`conversations.db`).
-   **Model Selection**: Dynamically fetches models from PCSS (e.g., `bielik_11b`, `DeepSeek-V3.1-vLLM`).
-   **Import/Export**: Save and load specific conversations to JSON files.
-   **Markdown Support**: Full rendering of headings, code blocks, and lists.

### 2. 🤖 Agent Mode (Autonomous)
The application features a powerful Agent capable of performing complex, multi-step tasks.

**File Management**
-   `list_directory`, `write_file`, `copy_file`, `move_file`, `delete_file`
-   `view_file` — read file content with **1-indexed line numbers** (auto-truncates to protect context limits).
-   `replace_file_content` — **precision line-based editing**: surgically targets specific code blocks via start/end line integers instead of brittle string matching.
-   `search_files` — cross-file pattern/string search across the workspace
-   `count_pattern_in_file` — count regex occurrences inside large logs efficiently

**Code & Data Execution**
-   `run_terminal` — sandboxed shell execution (e.g., `python app.py`) with strict workspace constraints and robust timeout / SIGKILL logic.
-   `run_python` — execute Python code snippets for calculations, data processing, and logic testing

**Internet & Research**
-   `search_web` — DuckDuckGo general search
-   `search_news` — DuckDuckGo latest news
-   `search_academic` — search PubMed/ArXiv/Semantic Scholar for academic papers
-   `visit_page` — fetch and extract full article text from a URL (up to 15,000 chars)
-   `deep_research` — **automated research pipeline**: runs multiple searches, visits top sources, summarizes each with AI, and returns a structured report

**Browser Automation (MCP)**
-   `playwright_*` — 33+ tools for headless browser control (navigate, click, type, screenshot) using **Model Context Protocol**

**Document Processing**
-   `read_pdf`, `read_docx`, `read_xlsx`, `save_document`, `convert_document` — read and generate files
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
    *   `readability-lxml` is a `pip`-only package and is **required** for the `visit_page` and `deep_research` tools to extract article content from web pages. It is already included in `environment.yml`.

### Setup Alternative (venv + pip)

Recommended if you prefer not to use Conda or encounter installation issues.

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/moondec/PCSS-frontend-LLM.git
    cd Bielik
    ```

2.  **Create and activate the virtual environment**

    **macOS / Linux:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

    **Windows:**
    ```cmd
    python -m venv venv
    venv\Scripts\activate
    ```

3.  **Install requirements**
    ```bash
    pip install --upgrade pip
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

1.  **API Key**: On first launch, enter your PCSS Cloud API Token (corresponds to your active Grant). See [MODEL_GUIDE.md](MODEL_GUIDE.md) for more information.
2.  **Workspace**: In **Settings**, select the directory where the Agent is allowed to operate (Default: `~/Documents/Bielik_Workspace`).

## ▶️ Usage

### 1. Activate Environment
- **Conda**: `conda activate bielik`
- **venv (macOS/Linux)**: `source venv/bin/activate`
- **venv (Windows)**: `venv\Scripts\activate`

### 2. Run Application
```bash
python pcss_llm_app/main.py
```

## ⚠️ Conda update

# Switch to base environment

conda activate base

# Update conda to the latest version

conda update -n base conda

## 🔄 Updating the Environment

When dependencies are added or updated (e.g., changes to `requirements.txt` or `environment.yml`), follow these steps:

1. **Pull latest changes**
   ```bash
   git pull
   ```

2. **Update dependencies**
   - **If using Conda**:
     ```bash
     conda env update --file environment.yml --prune
     ```
   - **If using venv**:
     ```bash
     pip install -r requirements.txt
     ```

### Tips
-   **Chat**: `Shift+Enter` for new lines, `Enter` to send.
-   **Agent**: Go to **Agent Mode** → **Create Assistant** to initialize the engine. Then type requests like:
    -   *"Perform deep research on AI in Poland and save the report to report.md"*
    -   *"Read report.pdf and create a summary summary.txt"*
    -   *"Write a Python script and run it to check the data"*

## 🔍 Troubleshooting

### 1. `ModuleNotFoundError: No module named 'PySide6'`
If after activating the environment (`conda activate` or `venv\Scripts\activate`) you still get a module not found error, it might be due to a conflict between multiple Python installations (e.g., Anaconda + Homebrew).
- **Symptom**: `pip list` shows PySide6, but `python main.py` throws an error.
- **Solution**: Check which Python executable is being used:
  ```bash
  which python
  python --version
  ```
  If the path points to a global installation instead of your `venv/bin/` or Conda `envs/` folder, you need to fix the symlinks in the environment (`ln -sf`) or use the full path to the interpreter.

### 2. DLL and SSL Issues on Windows (Conda + PySide6)
Conda environments on Windows do not always reliably load Qt libraries (DLLs). Additionally, Conda often "leaks" SSL environment variables into other virtual environments.
- **Solution**: The application includes a built-in mechanism in `main.py` that:
  - Automatically adds Conda/PySide6 DLL paths to `os.add_dll_directory`.
  - Clears incorrect `SSL_CERT_FILE` and `CURL_CA_BUNDLE` paths that might prevent connection to LLM models.

### 3. Playwright Issues (Agent Mode)
Browser tools require Node.js and installed drivers. If the Agent reports a Playwright error, run manually:
```bash
npx playwright install chromium
```

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
