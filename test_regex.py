import re
import json

output = """<minimax:tool_call>
<invoke name="list_directory
Action Input: {"dir_path": "curves"}
</invoke>
</minimax:tool_call>"""

# We look for <invoke name="action_name (closing quote optional)
minimax_invoke = re.search(
    r'<(?:minimax:)?tool_call[^>]*>\s*<invoke\s+name=["\']?([a-zA-Z0-9_]+)["\']?[^>]*?>?([\s\S]*?)</invoke>',
    output
)
if minimax_invoke:
    action = minimax_invoke.group(1).strip()
    params_block = minimax_invoke.group(2)
    print("Action:", action)
    print("Params block:", repr(params_block))
    
    # Is there an Action Input inside the params block? (It forgot to close the invoke tag or mixed them)
    action_input_match = re.search(r'Action Input:\s*({.*})', params_block, re.DOTALL)
    if action_input_match:
        print("Found Action Input inside invoke:", action_input_match.group(1))
    else:
        # standard parameters ...
        pass
else:
    print("No match")
