# Status Projektu - PCSS LLM App (v0.2.0)

Data aktualizacji: 2026-03-17

## Ostatnio wdrożone funkcjonalności

1. **Edytor kodu i eksplorator plików:**
   - Zintegrowano boczny pasek z drzewem plików (`QTreeView` + `QFileSystemModel`), który nasłuchuje zmian przestrzeni roboczej.
   - Dodano nową zakładkę w głównym oknie ze zintegrowanym edytorem kodu.
   - Wdrożono podświetlanie składni (nowy moduł `syntax_highlighter.py` wykorzystujący styl Monokai).
   - Zaimplementowano logikę otwierania i zapisywania plików bezpośrednio z edytora.

2. **Nowe profile agentów i narzędzia:**
   - Stworzono nowy, specjalistyczny profil agenta **"Recenzent - Reviewer"** (`reviewer.yaml`), skonstruowany do dogłębnej formalnej i strukturalnej analizy artykułów naukowych. Metodologia agenta obejmuje dwa etapy: weryfikację bibliografii oraz ewaluację struktury.
   - Zaimplementowano narzędzie `read_xlsx`.
   - Rozszerzono możliwości wszystkich standardowych profili agentów (m.in. DeepSeek, Qwen, Bielik, GLM-4) poprzez dodanie obsługi czytania dokumentów (narzędzia `read_pdf`, `read_docx`, `read_xlsx`).

3. **Dokumentacja i środowisko (v0.2.1):**
   - Przetłumaczono `README.md` w całości na język angielski (techniczne detale, lista funkcji, przykłady).
   - Rozwiązano błędy `RequestsDependencyWarning` oraz problemy z certyfikatami SSL w środowiskach `venv` (blokada wersji `urllib3<2.3.0`, dodanie `chardet/charset-normalizer`).
   - Dodano do `README.md` szczegółowy przewodnik instalacji przez `venv` dla macOS, Linux i Windows.
   - Wdrożono nową sekcję "Updating the Environment" ułatwiającą aktualizację zależności po zmianach w repozytorium.
   - Zsynchronizowano pliki `requirements.txt` oraz `environment.yml`.

## Stan obecny

- Pliki konfiguracyjne środowiska (`environment.yml`, `requirements.txt`) są w pełni zsynchronizowane i przetestowane pod kątem najczęstszych błędów instalacyjnych Windows/macOS.
- Dokumentacja `README.md` jest dostępna w języku angielskim, co ułatwia współpracę międzynarodową.
- Repozytorium zawiera jasne instrukcje aktualizacji środowiska.

## Następne kroki (do podjęcia w przyszłych sesjach)

- *Miejsce na zaplanowanie kolejnych iteracji i pomysłów (np. dalsze usprawnienia UI w edytorze kodu, nowe integracje z API, rozbudowa obsługi agentów).*
