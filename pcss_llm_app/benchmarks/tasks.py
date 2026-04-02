from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ChatTask:
    id: str
    category: str
    prompt: str

@dataclass
class AgentTask:
    id: str
    name: str
    description: str
    category: str
    prompt: str
    expected_tools: List[str]  # e.g. ["search_web", "view_file"]
    expected_count: int
    difficulty: str

# Standard chat benchmark tasks
CHAT_TASKS = [
    ChatTask("chat_001", "logic", "Jeżeli wszystkie koty mają ogony, a Mruczek jest kotem, to co możemy o nim powiedzieć? Uzasadnij krótko."),
    ChatTask("chat_002", "math", "Rozwiąż równanie: 2x + 5 = 15"),
    ChatTask("chat_003", "code", "Napisz funkcję w Pythonie, która sprawdza czy ciąg znaków jest palindromem."),
    ChatTask("chat_004", "creative", "Napisz krótkie, czterolinijkowe podsumowanie zalet sztucznej inteligencji rymem."),
    ChatTask("chat_005", "language", "Przetłumacz na poprawny polski: 'The quick brown fox jumps over the lazy dog' i wyjaśnij dlaczego to zdanie jest popularne.")
]

# Agent benchmark tasks targeting ACTUAL tools from pcss_llm_app.core.tools
AGENT_TASKS = [
    AgentTask(
        id="agent_001",
        name="Simple web search",
        description="Wyszukiwanie informacji w internecie",
        category="search",
        prompt="Znajdź w internecie, kto w minionym roku wygrał nagrodę Nobla z fizyki.",
        expected_tools=["search_web", "search_news"],
        expected_count=1,
        difficulty="easy"
    ),
    AgentTask(
        id="agent_002",
        name="File operations",
        description="Tworzenie i zapis plików",
        category="filesystem",
        prompt="Utwórz nowy plik o nazwie 'hello.txt' i zapisz w nim tekst 'Witaj świecie'.",
        expected_tools=["write_file"],
        expected_count=1,
        difficulty="easy"
    ),
    AgentTask(
        id="agent_003",
        name="Python execution",
        description="Wykonanie zaawansowanych obliczeń",
        category="computation",
        prompt="Użyj pythona aby obliczyć dokładną wartość (15.7 + 27.2) * 3.14 - 14",
        expected_tools=["run_python"],
        expected_count=1,
        difficulty="medium"
    ),
    AgentTask(
        id="agent_004",
        name="Complex workflow",
        description="Wyszukiwanie + Zapis do pliku",
        category="workflow",
        prompt="Znajdź informacje o aktualnej pogodzie w Warszawie za pomocą wyszukiwarki, a następnie zapisz krótkie podsumowanie tych informacji do pliku pogoda.txt.",
        expected_tools=["search_web", "write_file"],
        expected_count=2,
        difficulty="hard"
    ),
    AgentTask(
        id="agent_005",
        name="OS Terminal",
        description="Użycie terminala do pobrania nazwy systemu",
        category="system",
        prompt="Użyj terminala (wiersza poleceń), aby wypisać na ekranie nazwę systemu operacyjnego i wersję jądra/systemu (np. uname -a lub ver). Zwróć wynik z terminala do konwersacji.",
        expected_tools=["run_terminal"],
        expected_count=1,
        difficulty="medium"
    )
]
