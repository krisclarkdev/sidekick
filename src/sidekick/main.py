#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import threading
import itertools
import time
import requests
from pathlib import Path
from langchain_openai import ChatOpenAI
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.shortcuts import input_dialog

# --- UI Styling ---
style = Style.from_dict({
    'prompt': 'bold',
    'spinner': 'fg:cyan',
    'system': 'fg:yellow bold',
    'user': 'fg:green bold',
    'error': 'fg:red bold',
    'success': 'fg:green',
    'plan': 'fg:cyan',
    'test': 'fg:magenta',
})

def color_print(text, style_class):
    """Prints text in a given style."""
    colors = {
        'system': '\033[93m',  # Yellow
        'user': '\033[92m',  # Green
        'error': '\033[91m',  # Red
        'success': '\033[92m', # Green
        'plan': '\033[96m', # Cyan
        'test': '\033[95m', # Magenta
        'prompt': '\033[1m', # Bold
    }
    ENDC = '\033[0m'
    color = colors.get(style_class, '')
    print(f"{color}{text}{ENDC}", flush=True)


# --- Agent Tools ---
def create_file(path: str, content: str):
    """Creates a new file with the given content."""
    safe_path = Path(path).resolve()
    if not str(safe_path).startswith(str(Path.cwd().resolve())):
        color_print(
            f"SECURITY ERROR: Attempted to write to an unsafe path: {path}", 'error')
        return
    try:
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        color_print(f"✅ Created file: {path}", 'success')
    except Exception as e:
        color_print(f"Error creating file {path}: {e}", 'error')

def edit_file(path: str, content: str):
    """Overwrites an existing file with new content."""
    color_print(
        f"⚠️ Note: The 'edit_file' tool will completely overwrite the existing file.", 'system')
    create_file(path, content)

def execute_test(command: str):
    """Executes a shell command to test the code."""
    color_print(f"🚀 Running test: `{command}`", 'test')
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        print("--- TEST OUTPUT ---")
        print(result.stdout)
        print("--- END TEST ---")
        color_print("✅ Test completed successfully.", 'success')
    except subprocess.CalledProcessError as e:
        print("--- TEST FAILED ---")
        print(e.stdout)
        print("--- STDERR ---")
        print(e.stderr)
        print("--- END TEST ---")
        color_print(f"❌ Test failed with exit code {e.returncode}.", 'error')
    except subprocess.TimeoutExpired:
        color_print("❌ Test failed: Command timed out after 30 seconds.", 'error')
    except Exception as e:
        color_print(
            f"❌ An unexpected error occurred while running the test: {e}", 'error')

# --- Spinner Class for Progress Indication ---
class Spinner:
    def __init__(self, message="Thinking..."):
        self.message = message
        self._thread = None
        self.active = False

    def spin(self):
        spinner_chars = itertools.cycle(['⠇', '⠏', '⠋', '⠙', '⠹', '⠸', '⠼', '⠴'])
        while self.active:
            char = next(spinner_chars)
            # Using ANSI escape codes for color
            print(
                f"\r\033[96m{char}\033[0m {self.message}", end="", flush=True)
            time.sleep(0.1)
        # Clear the spinner line
        print("\r" + " " * (len(self.message) + 2) + "\r", end="", flush=True)

    def start(self):
        self.active = True
        self._thread = threading.Thread(target=self.spin, daemon=True)
        self._thread.start()

    def stop(self):
        if self.active:
            self.active = False
            if self._thread:
                self._thread.join(timeout=0.2)
# --- Main Application Logic ---
def get_model_choices(api_base):
    """Fetches the list of available models from the API."""
    try:
        response = requests.get(f"{api_base}/models")
        response.raise_for_status()
        models_data = response.json()
        return [model['id'] for model in models_data.get('data', [])]
    except requests.exceptions.RequestException as e:
        color_print(f"Error fetching models: {e}", 'error')
        return []

def clear_screen():
    """Clears the terminal screen."""
    # For Windows
    if os.name == 'nt':
        _ = os.system('cls')
    # For macOS and Linux
    else:
        _ = os.system('clear')

def main():
    # --- Configuration moved inside main for dynamic changes ---
    api_base = os.getenv("AI_AGENT_API_BASE", "http://localhost:1234/v1")
    current_model = os.getenv("AI_AGENT_MODEL", "default-model")
    api_key = os.getenv("AI_AGENT_API_KEY", "dummy-key")
    system_prompt = """
You are an expert software developer agent. Your goal is to help the user with their coding tasks by generating, editing, and testing files.

You must respond with a JSON object containing a list of actions to perform.
Each action is an object with a "command" key.

The available commands are:
1. "create_file": Creates a new file. Requires "path" and "content" keys.
2. "edit_file": Overwrites an existing file. Requires "path" and "content" keys.
3. "test": Runs a validation command in the shell. Requires a "test_command" key. The command should be simple and directly test the functionality of the code you just wrote.

If the user's request is not a coding task (e.g., a question, a poem), respond with a simple text answer without the JSON structure.

Example user request: "Create a python script that prints the 10th fibonacci number."
Your JSON response should be:
```json
{
  "actions": [
    {
      "command": "create_file",
      "path": "fibonacci.py",
      "content": "def fib(n):\\n    a, b = 0, 1\\n    for _ in range(n):\\n        a, b = b, a + b\\n    return a\\n\\nprint(fib(10))"
    },
    {
      "command": "test",
      "path": "fibonacci.py",
      "test_command": "python fibonacci.py"
    }
  ]
}
```

Now, fulfill the user's request.
"""

    clear_screen()
    session_history = FileHistory(os.path.expanduser('~/.sidekick_history'))
    command_completer = WordCompleter(['/help', '/exit', '/quit', '/model', '/llm_server', '/system_prompt'], ignore_case=True)
    prompt_session = PromptSession(
        history=session_history,
        auto_suggest=AutoSuggestFromHistory(),
        completer=command_completer,
        style=style
    )
    
    color_print(f"Welcome to Sidekick! Using model: {current_model}", 'system')
    color_print("Type /help for a list of commands.", 'system')

    # Session-level permissions
    allow_files_always = False
    allow_tests_always = False

    while True:
        try:
            prompt_text = "sidekick prompt > "
            user_prompt = prompt_session.prompt([('class:prompt', prompt_text)])

            if user_prompt.lower() in ["/exit", "/quit"]:
                break
            
            if user_prompt.lower() == "/help":
                print("\nAvailable Commands:")
                print("  /help           - Show this help message.")
                print("  /model          - Change the active AI model.")
                print("  /llm_server     - Change the LLM server API URL.")
                print("  /system_prompt  - View and edit the system prompt for this session.")
                print("  /exit           - Exit the application.")
                print()
                continue

            if user_prompt.lower() == "/system_prompt":
                color_print("\nEditing system prompt. Press Meta+Enter or Esc+Enter to finish.", 'system')
                new_system_prompt = prompt_session.prompt(
                    multiline=True,
                    default=system_prompt
                )
                
                if new_system_prompt:
                    system_prompt = new_system_prompt
                    color_print("\nSystem prompt updated for this session.", 'success')
                else:
                    color_print("\nSystem prompt update canceled.", 'system')
                print()
                continue

            if user_prompt.lower() == "/llm_server":
                new_api_base = input_dialog(
                    title="LLM Server Configuration",
                    text="Enter the API Base URL for your LLM server:",
                    default=api_base
                ).run()

                if new_api_base:
                    api_base = new_api_base
                    color_print(f"LLM Server URL updated to: {api_base}", 'success')
                else:
                    color_print("LLM Server URL update canceled.", 'system')
                continue

            if user_prompt.lower() == "/model":
                color_print("Fetching available models...", 'system')
                models = get_model_choices(api_base)
                if not models:
                    color_print("Could not retrieve models. Please check your server.", 'error')
                    continue
                
                print("\nPlease select a model:")
                for i, model in enumerate(models, 1):
                    print(f"  {i}. {model}")
                
                try:
                    choice = int(input("Enter number: ")) - 1
                    if 0 <= choice < len(models):
                        current_model = models[choice]
                        color_print(f"Model changed to: {current_model}", 'success')
                    else:
                        color_print("Invalid selection.", 'error')
                except ValueError:
                    color_print("Invalid input. Please enter a number.", 'error')
                continue

            spinner = Spinner()
            response_container = {"response": None, "error": None}

            def get_llm_response():
                try:
                    llm = ChatOpenAI(
                        model=current_model, openai_api_base=api_base, openai_api_key=api_key)
                    full_prompt = f"{system_prompt}\nUser Request: {user_prompt}"
                    response_container["response"] = llm.invoke(full_prompt)
                except Exception as e:
                    response_container["error"] = e
            
            spinner.start()
            llm_thread = threading.Thread(target=get_llm_response, daemon=True)
            llm_thread.start()
            llm_thread.join()
            spinner.stop()

            if response_container["error"]:
                color_print(f"\nAn error occurred: {response_container['error']}", 'error')
                continue
            
            response = response_container["response"]
            response_text = response.content

            if "```json" not in response_text:
                color_print(f"\n🤖 Sidekick:\n{response_text}", 'system')
                continue

            try:
                json_plan_str = response_text.split("```json")[1].split("```")[0].strip()
                plan = json.loads(json_plan_str)
            except (json.JSONDecodeError, IndexError) as e:
                color_print(f"\nCould not parse the AI's plan. Error: {e}", 'error')
                color_print(f"Raw response:\n{response_text}", 'system')
                continue

            actions = plan.get("actions", [])
            file_actions = [a for a in actions if a.get("command") in ["create_file", "edit_file"]]
            test_actions = [a for a in actions if a.get("command") == "test"]

            if file_actions:
                if not allow_files_always:
                    print()
                    color_print("🤖 Sidekick has proposed the following file changes:", 'plan')
                    for i, action in enumerate(file_actions, 1):
                        print(f"  {i}. {action['command']} on file '{action['path']}'")
                    
                    confirm = input(
                        "\nApply these file changes? [y/N/always]: ").lower()
                    if confirm == 'always':
                        allow_files_always = True
                    if confirm in ['y', 'always']:
                        for action in file_actions:
                            action_func = create_file if action["command"] == "create_file" else edit_file
                            action_func(action["path"], action["content"])
                    else:
                        print("File changes aborted.")
                        continue
                else:
                    for action in file_actions:
                        action_func = create_file if action["command"] == "create_file" else edit_file
                        action_func(action["path"], action["content"])

            if test_actions:
                if not allow_tests_always:
                    print()
                    color_print("🤖 Sidekick has proposed the following tests:", 'plan')
                    for i, action in enumerate(test_actions, 1):
                        print(f"  {i}. Run command: `{action['test_command']}`")
                    
                    confirm_test = input(
                        "\nRun these tests? [y/N/always]: ").lower()
                    if confirm_test == 'always':
                        allow_tests_always = True
                    if confirm_test in ['y', 'always']:
                        for action in test_actions:
                            execute_test(action["test_command"])
                    else:
                        print("Tests skipped.")
                else:
                    for action in test_actions:
                        execute_test(action["test_command"])
        
        except KeyboardInterrupt:
            print("\nExiting. Goodbye!")
            break
        except Exception as e:
            color_print(f"\nAn unexpected error occurred: {e}", 'error')
            
if __name__ == "__main__":
    main()


