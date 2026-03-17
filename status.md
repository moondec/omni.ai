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

3. **Inne poprawki:**
   - Rozwiązano problem z instalacją `PySide6` na systemie Windows (przeniesienie do `pip`) zapobiegając błędom ładowania bibliotek DLL.
   - Przeprowadzono audyt importów w kodzie i zsynchronizowano `environment.yml` oraz instalację w `README.md` (dodano brakujące paczki: `numpy`, `pandas`, `pygments`, `pydantic`, zmieniono `ddgs` na `duckduckgo-search` oraz `PyPDF2` na `pypdf`).
   - Dokonano wydania wersji `0.2.0` (zaktualizowano `__init__.py` i interfejs UI).
   - Zaktualizowano `CHANGELOG.md` oraz repozytorium Git (commit & push).

## Stan obecny

- Pliki konfiguracyjne środowiska idealnie odzwierciedlają aktualny kod aplikacji.
- Kod w repozytorium jest zsynchronizowany (`git status` na gałęzi `main` wykazuje czyste drzewo robocze przed ostatnimi poprawkami zależności).
- Wszystkie zadania z najnowszego planu wdrożeniowego (związanego z UI edytora i agentami) zostały zrealizowane.

## Następne kroki (do podjęcia w przyszłych sesjach)

- *Miejsce na zaplanowanie kolejnych iteracji i pomysłów (np. dalsze usprawnienia UI w edytorze kodu, nowe integracje z API, rozbudowa obsługi agentów).*
