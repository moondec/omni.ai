# Agent Benchmark Report (mock)

### Agent Metrics (MOCK)

| Model | Success | Tool Acc | Avg Time (ms) |
|-------|---------|----------|---------------|
| DeepSeek-V3.1-vLLM | 0.0% | 0.0% | 10199.7 |
| DeepSeek-V3.1-vLLM-2 | 0.0% | 0.0% | 10946.6 |
| Mistral-Small-3.2:24b | 100.0% | 100.0% | 1787.6 |
| Qwen2.5:72b | 100.0% | 100.0% | 2831.5 |
| bielik_11b | 0.0% | 0.0% | 8406.5 |
| gpt-oss_120b | 100.0% | 100.0% | 1659.6 |
| llama3.3:70b | 80.0% | 80.0% | 1584.5 |
| Nanonets-OCR-s | 0.0% | 0.0% | 809.0 |
| Qwen3-Coder-Next | 80.0% | 80.0% | 668.2 |
| MiniMax-M2.5 | 100.0% | 100.0% | 2249.1 |
| Qwen3-VL-235B-A22B-Instruct | 100.0% | 100.0% | 1782.3 |
| GLM-4.7 | 100.0% | 100.0% | 6137.4 |
| Qwen3.5-397B-A17B | 100.0% | 100.0% | 2891.6 |
| Qwen3.5-397B-A17B-GPTQ-Int4 | 100.0% | 100.0% | 3082.0 |


### Task Details

#### DeepSeek-V3.1-vLLM
- **agent_001**: Success=False, Acc=0.0
  - Called: [] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=False, Acc=0.0
  - Called: [] (Expected: ['run_python'])
- **agent_003**: Success=False, Acc=0.0
  - Called: [] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=False, Acc=0.0
  - Called: [] (Expected: ['save_document'])
- **agent_005**: Success=False, Acc=0.0
  - Called: [] (Expected: ['search_web', 'search_academic'])
#### DeepSeek-V3.1-vLLM-2
- **agent_001**: Success=False, Acc=0.0
  - Called: [] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=False, Acc=0.0
  - Called: [] (Expected: ['run_python'])
- **agent_003**: Success=False, Acc=0.0
  - Called: [] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=False, Acc=0.0
  - Called: [] (Expected: ['save_document'])
- **agent_005**: Success=False, Acc=0.0
  - Called: [] (Expected: ['search_web', 'search_academic'])
#### Mistral-Small-3.2:24b
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=True, Acc=1.0
  - Called: ['view_file'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
#### Qwen2.5:72b
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=True, Acc=1.0
  - Called: ['view_file', 'count_pattern_in_file', 'run_terminal'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
#### bielik_11b
- **agent_001**: Success=False, Acc=0.0
  - Called: [] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=False, Acc=0.0
  - Called: [] (Expected: ['run_python'])
- **agent_003**: Success=False, Acc=0.0
  - Called: [] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=False, Acc=0.0
  - Called: [] (Expected: ['save_document'])
- **agent_005**: Success=False, Acc=0.0
  - Called: [] (Expected: ['search_web', 'search_academic'])
#### gpt-oss_120b
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=True, Acc=1.0
  - Called: ['view_file'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
#### llama3.3:70b
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=False, Acc=0.0
  - Called: ['count_pattern_in_file'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
#### Nanonets-OCR-s
- **agent_001**: Success=False, Acc=0.0
  - Called: [] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=False, Acc=0.0
  - Called: [] (Expected: ['run_python'])
- **agent_003**: Success=False, Acc=0.0
  - Called: [] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=False, Acc=0.0
  - Called: [] (Expected: ['save_document'])
- **agent_005**: Success=False, Acc=0.0
  - Called: [] (Expected: ['search_web', 'search_academic'])
#### Qwen3-Coder-Next
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=False, Acc=0.0
  - Called: ['read_docx'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
#### MiniMax-M2.5
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=True, Acc=1.0
  - Called: ['view_file'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
#### Qwen3-VL-235B-A22B-Instruct
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=True, Acc=1.0
  - Called: ['view_file', 'count_pattern_in_file', 'run_terminal'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
#### GLM-4.7
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=True, Acc=1.0
  - Called: ['view_file'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
#### Qwen3.5-397B-A17B
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=True, Acc=1.0
  - Called: ['view_file'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
#### Qwen3.5-397B-A17B-GPTQ-Int4
- **agent_001**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'run_python', 'write_file'])
- **agent_002**: Success=True, Acc=1.0
  - Called: ['run_python'] (Expected: ['run_python'])
- **agent_003**: Success=True, Acc=1.0
  - Called: ['view_file'] (Expected: ['view_file', 'run_terminal'])
- **agent_004**: Success=True, Acc=1.0
  - Called: ['save_document'] (Expected: ['save_document'])
- **agent_005**: Success=True, Acc=1.0
  - Called: ['search_web'] (Expected: ['search_web', 'search_academic'])
