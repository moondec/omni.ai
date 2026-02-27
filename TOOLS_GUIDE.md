# Agent Tools Guide

This document describes the tools available to the Autonomous Agent in the PCSS LLM Client. The agent automatically selects the best tool for the job.

> [!IMPORTANT]
> **Workspace Sandboxing:** For security, the agent is strictly confined to the directory defined in Settings. It cannot read or write files outside this path. Absolute paths and traversal attempts are automatically blocked.

## 📂 File Management
Basic and advanced operations within the workspace.
*   **list_directory**: Lists files and folders.
*   **create_directory**: Creates a new folder.
*   **read_file**: Reads contents of text files.
*   **write_file**: Creates or overwrites text files.
*   **edit_file** ⭐ (New): 
    *   *Function:* Replaces a specific block of text in a file.
    *   *Advantage:* Much safer for large files as it doesn't overwrite the whole file. Requires an exact match of the target block.
*   **search_files** ⭐ (New):
    *   *Function:* Searches for a string across all files in the workspace (or matching a pattern like `*.py`).
*   **copy_file / move_file / delete_file**: Standard file operations.

## 🐍 Code & Data
*   **run_python** ⭐ (New):
    *   *Function:* Executes Python code in a secure sandbox.
    *   *Capabilities:* Includes `math`, `json`, `numpy`, `pandas`, and `matplotlib`.
    *   *Security:* File operations are restricted to the workspace. No access to `os.system` or `subprocess`.
*   **generate_chart**:
    *   *Function:* Creates bar, line, pie, or scatter charts from data and saves them as PNG/JPG.

## 📄 Document Processing
*   **read_docx / read_pdf**: Extracts text from DOCX and PDF files.
*   **save_document** ⭐ (Recommended):
    *   *Function:* Creates formatted PDF, DOCX, HTML, or TXT from HTML-formatted content.
    *   *Features:* Automatically downloads and embeds remote images into the final document.
*   **convert_document**: Converts files between formats using Pandoc.

## 🌐 Internet & Research
*   **search_web**: General DuckDuckGo search for links/snippets.
*   **search_news**: Specialized search for the latest news articles.
*   **visit_page**: 
    *   *Function:* Fetches full text from a URL. 
    *   *Limit:* Supports up to **15,000 characters** per page.
    *   *Capability:* Uses `readability` to strip ads and extract the main article content.
*   **deep_research** ⭐⭐⭐ (New):
    *   *Function:* Automates complex research. It generates multiple search queries, visits several top sources, summarizes them using AI, and presents a consolidated report.

## 👁️ OCR & Vision
*   **ocr_image**: Extracts text from photos and scans using **Nanonets-OCR-s**.
*   **analyze_image**: Multi-modal analysis. 
    *   *Note:* Requires a vision-capable model like `Qwen3-VL-235B-A22B-Instruct`.

## 🤖 Example Prompts
*   *"Conduct deep research on AI trends in Poland and save a summary PDF."* (Uses `deep_research` -> `save_document`)
*   *"Search for 'ConfigManager' in all python files."* (Uses `search_files`)
*   *"Write a script to calculate the average of sales.csv and show it on a bar chart."* (Uses `run_python` -> `generate_chart`)
