# Agent Benchmark Report (mock)

### Agent Metrics (MOCK)

| Model | Success | Tool Acc | Avg Time (ms) |
|-------|---------|----------|---------------|
| Mistral-Small-3.2:24b | 100.0% | 100.0% | 1670.6 |


### Task Details

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
  - Called: ['search_web'] (Expected: ['search_web'])
