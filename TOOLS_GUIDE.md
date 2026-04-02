# Agent Tools Guide

This document describes the tools available to the Autonomous Agent in the PCSS LLM Client. The agent automatically selects the best tool for the job.

> [!IMPORTANT]
> **Workspace Sandboxing:** For security, the agent is strictly confined to the directory defined in Settings. It cannot read or write files outside this path. Absolute paths and traversal attempts are automatically blocked.

## 📂 File Management
Basic and advanced operations within the workspace.
*   **list_directory**: Lists files and folders.
*   **create_directory**: Creates a new folder.
*   **view_file** ⭐ (New):
    *   *Function:* Reads contents of text files and prepends **1-indexed line numbers** to every line. This is crucial for making precise edits. (Auto-truncates large files).
*   **write_file**: Creates or overwrites text files.
*   **replace_file_content** ⭐ (New): 
    *   *Function:* Surgically replaces a specific block of text based on an exact integer line range (`start_line`, `end_line`).
    *   *Advantage:* Extremely safe for large files; bypasses the string-matching escaping bugs inherent to weak LLMs.
*   **search_files** ⭐ (New):
    *   *Function:* Searches for a string across all files in the workspace (or matching a pattern like `*.py`).
*   **count_pattern_in_file** ⭐ (New):
    *   *Function:* Efficiently counts occurrences of a regex pattern in a specific file. Great for analyzing large log files without loading them into memory.
*   **copy_file / move_file / delete_file**: Standard file operations.

## 🐍 Code & Data
*   **run_terminal** ⭐ (New):
    *   *Function:* Executes shell commands (e.g., `python script.py`, `npm start`) directly in the workspace.
    *   *Safety:* Strict timeout and SIGKILL process management protect the application from hanging servers.
*   **run_python**:
    *   *Function:* Executes Python code in a secure sandbox.
    *   *Capabilities:* Includes `math`, `json`, `numpy`, `pandas`, and `matplotlib`.
    *   *Security:* File operations are restricted to the workspace. No access to `os.system` or `subprocess`.
*   **generate_chart**:
    *   *Function:* Creates bar, line, pie, or scatter charts from data and saves them as PNG/JPG.

## 📄 Document Processing
*   **read_docx / read_pdf / read_xlsx**: Extracts text/data from DOCX, PDF, and Excel spreadsheet files.
*   **save_document** ⭐ (Recommended):
    *   *Function:* Creates formatted PDF, DOCX, HTML, or TXT from HTML-formatted content.
    *   *Features:* Automatically downloads and embeds remote images into the final document.
*   **convert_document**: Converts files between formats using Pandoc.

## 🌐 Internet & Research
*   **search_web**: General DuckDuckGo search for links/snippets.
*   **search_news**: Specialized search for the latest news articles.
*   **search_academic** ⭐ (New):
    *   *Function:* Searches PubMed/ArXiv/etc for peer-reviewed academic papers.
*   **visit_page**: 
    *   *Function:* Fetches full text from a URL. 
    *   *Limit:* Supports up to **15,000 characters** per page.
    *   *Capability:* Uses `readability` to strip ads and extract the main article content.
*   **deep_research** ⭐⭐⭐ (New):
    *   *Function:* Automates complex research. It generates multiple search queries, visits several top sources, summarizes them using AI, and presents a consolidated report.

## 🧠 Memory & Context
*   **update_context** ⭐ (New):
    *   *Function:* Allows the agent to write persistent briefing notes into a hidden `.agent_context.md` file. It ensures the agent "remembers" project state across different chat sessions or restarts.

## 🌐 Browser Automation (MCP)
Powered by the **Model Context Protocol** and Playwright.
*   **playwright_navigate / playwright_screenshot**:
    *   *Function:* Navigates to a website and takes visual snapshots of the rendered page.
*   **playwright_click / playwright_fill / playwright_evaluate**:
    *   *Function:* Interacted with web elements (buttons, forms) and executes custom JavaScript.
*   **playwright_select_option / playwright_get_interactive_elements**:
    *   *Function:* Selects elements in dropdowns and retrieves all clickable bounding boxes on the page.
*   **playwright_get_visible_text / playwright_get_visible_html**:
    *   *Function:* Retrieves clean textual or HTML representation of the currently visible screen area.
*   **Limitations & Requirements:**
    *   **Headless:** The browser runs entirely in the background. No window will appear.
    *   **Installation:** Requires `npx playwright install chromium` to be executed once on the machine.
    *   **Persistent Session ⭐ (New)**: Upgraded architecture now uses a dedicated background worker. The browser context **remains alive** across multiple tool calls, allowing the agent to log in, navigate, and perform complex multi-step interactions seamlessly.

## 👁️ OCR & Vision
*   **ocr_image**: Extracts text from photos and scans using **Nanonets-OCR-s**.
*   **analyze_image** ⭐ (Active):
    *   *Function:* Multi-modal analysis of images.
    *   *Capabilities:* Uses **Qwen3-VL-235B-A22B-Instruct** on PCSS to describe scenes, understand charts, and analyze visual layouts.

## 🤖 Example Prompts
*   *"Conduct deep research on AI trends in Poland and save a summary PDF."* (Uses `deep_research` -> `save_document`)
*   *"Search for 'ConfigManager' in all python files."* (Uses `search_files`)
*   *"Write a script to calculate the average of sales.csv and show it on a bar chart."* (Uses `run_python` -> `generate_chart`)
