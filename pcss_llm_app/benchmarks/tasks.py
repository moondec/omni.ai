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

# Standard chat benchmark tasks - DIFFICULT SAMPLES
CHAT_TASKS = [
    ChatTask(
        "chat_001", 
        "logic_reasoning", 
        "Problem: Przewoźnik musi przewieźć przez rzekę wilka, kozę i kapustę. Łódka jest tak mała, że mieści tylko jego i jeden z obiektów. Wilk nie może zostać sam z kozą (bo ją zje), a koza nie może zostać sama z kapustą. DODATKOWY WARUNEK: Wilk panicznie boi się wody i jeśli zostanie na brzegu sam bez opieki człowieka przez więcej niż dwa kursy, ucieknie do lasu. Podaj najkrótszą sekwencję ruchów, która rozwiązuje ten problem, biorąc pod uwagę nowy warunek."
    ),
    ChatTask(
        "chat_002", 
        "code_architecture", 
        "Oceń poniższy fragment kodu w Pythonie (Pydantic V2). Czy widzisz w nim potencjalne problemy z wydajnością lub logiką przy skali 1 mln rekordów? Zaproponuj optymalizację: \n\n```python\nfrom pydantic import BaseModel, field_validator\nfrom typing import List\n\nclass DataPoint(BaseModel):\n    id: int\n    values: List[float]\n    \n    @field_validator('values')\n    def check_values(cls, v):\n        if sum(v) > 1000:\n            raise ValueError('Too high')\n        return v\n\nclass Batch(BaseModel):\n    items: List[DataPoint]\n```"
    ),
    ChatTask(
        "chat_003", 
        "complex_formatting", 
        "Stwórz poprawny obiekt JSON reprezentujący strukturę firmy. Musi zawierać: 3 działy, w każdym min. 2 pracowników z zagnieżdżonymi listami umiejętności. WAŻNE: Wartości tekstowe 'opis' nie mogą zawierać żadnych znaków nowej linii (\\n) ani tabulacji, a cały JSON musi być w jednej linii (minified). Każdy pracownik musi mieć unikalny identyfikator UUID."
    ),
    ChatTask(
        "chat_004", 
        "mathematical_logic", 
        "Ile wynosi suma cyfr liczby 2^1000? Opisz krótko metodę, jak byś to obliczył programistycznie, a następnie podaj oszacowanie rzędu wielkości samej liczby (ile ma cyfr)."
    ),
    ChatTask(
        "chat_005", 
        "linguistic_nuance", 
        "Wyjaśnij różnicę między terminami 'implicite' a 'explicite' w kontekście projektowania interfejsów API. Podaj przykład kodu (pseudo-kod), gdzie ta różnica ma kluczowe znaczenie dla bezpieczeństwa systemu."
    )
]

# Agent benchmark tasks targeting ACTUAL tools - MULTI-STEP WORKFLOWS
AGENT_TASKS = [
    AgentTask(
        id="agent_001",
        name="Cascade Research & Math",
        description="Wyszukiwanie -> Obliczenia -> Zapis",
        category="workflow",
        prompt="Sprawdź w internecie dokładny rok, w którym Alexander Fleming odkrył penicylinę. Następnie użyj Pythona (run_python), aby obliczyć ile pełnych dekad upłynęło od tego roku do dzisiaj (2025). Wynik (samą liczbę dekad) zapisz do pliku 'nobel_stats.txt'.",
        expected_tools=["search_web", "run_python", "write_file"],
        expected_count=3,
        difficulty="hard"
    ),
    AgentTask(
        id="agent_002",
        name="Data Analysis Stress Test",
        description="Generowanie dużych danych i analiza wzorców",
        category="computation",
        prompt="Użyj narzędzia run_python, aby obliczyć wartość 17 do potęgi 123. Przekonwertuj wynik na ciąg znaków (string) i policz, ile razy występuje w nim cyfra '7'. Zwróć tylko wynik końcowy (liczbę wystąpień).",
        expected_tools=["run_python"],
        expected_count=1,
        difficulty="medium"
    ),
    AgentTask(
        id="agent_003",
        name="Self-Reflection & System Audit",
        description="Analiza plików projektu i weryfikacja systemowa",
        category="system",
        prompt="Przeczytaj zawartość pliku 'CLAUDE.md' w bieżącym katalogu. Policz ile razy występuje w nim słowo 'PCSS' (niezależnie od wielkości liter). Następnie użyj terminala (run_terminal) i polecenia 'grep' lub 'wc' aby zweryfikować ten wynik. Porównaj obie liczby w swojej odpowiedzi.",
        expected_tools=["view_file", "run_terminal"],
        expected_count=2,
        difficulty="hard"
    ),
    AgentTask(
        id="agent_004",
        name="Document Generation & Formatting",
        description="Tworzenie sformatowanych dokumentów",
        category="document",
        prompt="Stwórz profesjonalny raport w formacie PDF o nazwie 'AI_Safety.pdf'. Treść raportu powinna zawierać nagłówek H1 'Zasady Bezpieczeństwa AI', listę punktowaną z 3 kluczowymi zasadami oraz krótkie podsumowanie. Użyj narzędzia save_document.",
        expected_tools=["save_document"],
        expected_count=1,
        difficulty="medium"
    ),
    AgentTask(
        id="agent_005",
        name="Multi-Hop Fact Verification",
        description="Weryfikacja faktów z wielu źródeł",
        category="search",
        prompt="Znajdź aktualnego dyrektora PCSS (Poznańskie Centrum Superkomputerowo-Sieciowe). Następnie wyszukaj, na jakiej uczelni wyższej ta osoba uzyskała stopień naukowy doktora. Podaj nazwę tej uczelni.",
        expected_tools=["search_web", "search_academic"],
        expected_count=2,
        difficulty="hard"
    )
]
