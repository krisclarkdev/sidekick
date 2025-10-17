#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import List, Optional
import requests
from langchain_openai import ChatOpenAI
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

# --- Configuration ---
# The agent will look for these environment variables. If not found, it uses the default values.
# You can set these in your ~/.bashrc, ~/.zshrc, or your system's environment variable settings.
MODEL_NAME = os.getenv("AI_AGENT_MODEL", "TheBloke/DeepSeek-Coder-V2-Lite-Instruct-AWQ")
API_BASE = os.getenv("AI_AGENT_API_BASE", "http://localhost:1234/v1")
API_KEY = os.getenv("AI_AGENT_API_KEY", "dummy-key") # Required but not validated by local servers

# --- UI Colors and Styles ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# --- Define the Agent's Tools ---

def create_file(path: str, content: str):
    """Creates a new file with the given content."""
    safe_path = Path(path).resolve()
    if not str(safe_path).startswith(str(Path.cwd().resolve())):
        print(f"{Colors.RED}❌ SECURITY ERROR: Attempted to write to an unsafe path: {path}{Colors.ENDC}")
        return
    try:
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"{Colors.GREEN}✅ Created file: {path}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.RED}❌ Error creating file {path}: {e}{Colors.ENDC}")

def edit_file(path: str, content: str):
    """Overwrites an existing file with new content."""
    print(f"{Colors.YELLOW}⚠️ Note: The 'edit_file' tool will completely overwrite the existing file.{Colors.ENDC}")
    create_file(path, content)

def execute_test(command: str):
    """Executes a shell command to test the code."""
    print(f"{Colors.BLUE}🚀 Running test: `{command}`{Colors.ENDC}")
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=30 # Add a timeout for safety
        )
        print(f"{Colors.GREEN}--- TEST OUTPUT ---{Colors.ENDC}")
        print(result.stdout)
        print(f"{Colors.GREEN}--- END TEST ---{Colors.ENDC}")
        print(f"{Colors.GREEN}✅ Test completed successfully.{Colors.ENDC}")
    except subprocess.CalledProcessError as e:
        print(f"{Colors.RED}--- TEST FAILED ---{Colors.ENDC}")
        print(e.stdout)
        print(f"{Colors.RED}--- STDERR ---{Colors.ENDC}")
        print(e.stderr)
        print(f"{Colors.RED}--- END TEST ---{Colors.ENDC}")
        print(f"{Colors.RED}❌ Test failed with exit code {e.returncode}.{Colors.ENDC}")
    except subprocess.TimeoutExpired:
        print(f"{Colors.RED}❌ Test failed: Command timed out after 30 seconds.{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.RED}❌ An unexpected error occurred while running the test: {e}{Colors.ENDC}")

def fetch_available_models(api_base: str, api_key: str) -> Optional[List[str]]:
    """Fetches the list of available models from the OpenAI-compatible endpoint."""
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(f"{api_base}/models", headers=headers, timeout=10)
        response.raise_for_status() # Raise an exception for bad status codes
        models_data = response.json()
        # The model IDs are usually in a list under the 'data' key
        model_ids = [model['id'] for model in models_data.get('data', [])]
        return sorted(model_ids)
    except requests.exceptions.RequestException as e:
        print(f"{Colors.RED}❌ Could not fetch models: {e}{Colors.ENDC}")
        return None

# --- The "Tool-Use" Prompt (Updated for Testing) ---
SYSTEM_PROMPT = """
You are an expert software developer agent. Your goal is to help the user with their coding tasks by generating, editing, and testing files.

You must respond with a JSON object containing a list of actions to perform.
Each action is an object with a "command" key.

The available commands are:
1. "create_file": Creates a new file. Requires "path" and "content" keys.
2. "edit_file": Overwrites an existing file. Requires "path" and "content" keys.
3. "test": Runs a validation command in the shell. Requires a "test_command" key. The command should be simple and directly test the functionality of the code you just wrote.

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

class Spinner:
    """A simple spinner class to show progress."""
    def __init__(self, message="Thinking..."):
        self.message = message
        self.running = False
        self.thread = None

    def _spin(self):
        chars = "|/-\\"
        while self.running:
            for char in chars:
                sys.stdout.write(f"\r{Colors.HEADER}{self.message} {char}{Colors.ENDC}")
                sys.stdout.flush()
                time.sleep(0.1)
        sys.stdout.write(f"\r{' ' * (len(self.message) + 2)}\r") # Clear line
        sys.stdout.flush()
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin)
        self.thread.daemon = True # Set as daemon thread
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

def get_llm_response(llm, prompt):
    """Function to run in a separate thread to get the LLM response."""
    try:
        return llm.invoke(prompt)
    except Exception as e:
        # We can't print directly from the thread, so we return the exception
        return e

def main():
    if not API_BASE:
        print(f"{Colors.RED}❌ Configuration Error: AI_AGENT_API_BASE environment variable is not set.{Colors.ENDC}")
        sys.exit(1)
    
    current_model_name = MODEL_NAME
    llm = ChatOpenAI(model=current_model_name, openai_api_base=API_BASE, openai_api_key=API_KEY)
    
    always_allow_files = False
    always_allow_tests = False
    
    print(f"{Colors.BOLD}AI Agent Initialized. Type '/help' for commands.{Colors.ENDC}")

    session = PromptSession()

    while True:
        try:
            terminal_width = os.get_terminal_size().columns
            separator = '─' * terminal_width
            print(f"\n{Colors.BLUE}{separator}{Colors.ENDC}")
            
            prompt_html = HTML(f'<b><ansigreen>klaude prompt &gt; </ansigreen></b>')
            user_prompt = session.prompt(prompt_html)

            if user_prompt.startswith('/'):
                command = user_prompt.lower().strip()
                if command in ['/exit', '/quit']:
                    print(f"{Colors.YELLOW}Session ended.{Colors.ENDC}")
                    break
                elif command == '/help':
                    print(f"\n{Colors.BOLD}Available commands:{Colors.ENDC}")
                    print(f"  {Colors.CYAN}/help{Colors.ENDC}    - Show this help message.")
                    print(f"  {Colors.CYAN}/model{Colors.ENDC}   - Change the currently active model.")
                    print(f"  {Colors.CYAN}/exit{Colors.ENDC}    - Exit the session.")
                    continue
                elif command == '/model':
                    print(f"{Colors.YELLOW}Fetching available models...{Colors.ENDC}")
                    models = fetch_available_models(API_BASE, API_KEY)
                    if models:
                        print(f"\n{Colors.BOLD}Current Model: {Colors.CYAN}{current_model_name}{Colors.ENDC}")
                        print(f"{Colors.BOLD}Please select a new model:{Colors.ENDC}")
                        for i, model_id in enumerate(models):
                            print(f"  {Colors.YELLOW}{i + 1}.{Colors.ENDC} {model_id}")
                        
                        try:
                            selection = input(f"\nEnter number (or press Enter to cancel): ")
                            if not selection:
                                print("Model change cancelled.")
                                continue
                            
                            selected_index = int(selection) - 1
                            if 0 <= selected_index < len(models):
                                current_model_name = models[selected_index]
                                llm = ChatOpenAI(model=current_model_name, openai_api_base=API_BASE, openai_api_key=API_KEY)
                                print(f"{Colors.GREEN}✅ Model changed to: {current_model_name}{Colors.ENDC}")
                            else:
                                print(f"{Colors.RED}Invalid selection.{Colors.ENDC}")
                        except ValueError:
                            print(f"{Colors.RED}Invalid input. Please enter a number.{Colors.ENDC}")
                    continue
                else:
                    print(f"{Colors.RED}Unknown command: {command}. Type /help for available commands.{Colors.ENDC}")
                    continue

            full_prompt = f"{SYSTEM_PROMPT}\nUser Request: {user_prompt}"
            
            spinner = Spinner("🧠 Thinking...")
            response = None
            
            spinner.start()
            response = get_llm_response(llm, full_prompt)
            spinner.stop()

            if isinstance(response, Exception):
                raise response

            response_text = response.content

            if "```json" in response_text:
                try:
                    json_plan_str = response_text.split("```json")[1].split("```")[0].strip()
                    plan = json.loads(json_plan_str)
                    
                    actions = plan.get("actions", [])
                    file_actions = [a for a in actions if a["command"] in ["create_file", "edit_file"]]
                    test_actions = [a for a in actions if a["command"] == "test"]

                    if file_actions:
                        print(f"\n{Colors.HEADER}{Colors.BOLD}🤖 AI has proposed the following file changes:{Colors.ENDC}")
                        for i, action in enumerate(file_actions, 1):
                            print(f"  {Colors.YELLOW}{i}.{Colors.ENDC} {Colors.BOLD}{action['command'].replace('_', ' ').title()}{Colors.ENDC} on file '{Colors.CYAN}{action['path']}{Colors.ENDC}'")
                        
                        if not always_allow_files:
                            prompt_text = f"\n{Colors.YELLOW}Do you want to apply these file changes? [y/N/a (always)]: {Colors.ENDC}"
                            confirm = input(prompt_text).lower()
                            if confirm == 'a':
                                always_allow_files = True
                            elif confirm != 'y':
                                print("Aborted.")
                                continue
                        
                        if always_allow_files or confirm in ['y', 'a']:
                            for action in file_actions:
                                if action["command"] == "create_file":
                                    create_file(action["path"], action["content"])
                                elif action["command"] == "edit_file":
                                    edit_file(action["path"], action["content"])

                    if test_actions:
                        print(f"\n{Colors.HEADER}{Colors.BOLD}🤖 AI has proposed the following tests:{Colors.ENDC}")
                        for i, action in enumerate(test_actions, 1):
                            print(f"  {Colors.YELLOW}{i}.{Colors.ENDC} Run command: {Colors.CYAN}`{action['test_command']}`{Colors.ENDC}")
                        
                        if not always_allow_tests:
                            prompt_text = f"\n{Colors.YELLOW}Do you want to run these tests? [y/N/a (always)]: {Colors.ENDC}"
                            confirm_test = input(prompt_text).lower()
                            if confirm_test == 'a':
                                always_allow_tests = True
                            elif confirm_test != 'y':
                                print("Tests skipped.")
                                continue
                        
                        if always_allow_tests or confirm_test in ['y', 'a']:
                            for action in test_actions:
                                execute_test(action["test_command"])

                except (IndexError, json.JSONDecodeError):
                    print(f"\n{Colors.RED}❌ Failed to parse the AI's plan. It might be malformed.{Colors.ENDC}")
                    print(f"{Colors.YELLOW}--- AI Raw Response ---{Colors.ENDC}")
                    print(response_text)
                    print(f"{Colors.YELLOW}-----------------------{Colors.ENDC}")
            else:
                print(f"\n{Colors.HEADER}{Colors.BOLD}🤖 Response:{Colors.ENDC}")
                print(response_text)

        except KeyboardInterrupt:
            spinner.stop()
            print(f"\n\n{Colors.YELLOW}Session ended by user.{Colors.ENDC}")
            break
        except Exception as e:
            spinner.stop()
            print(f"\n{Colors.RED}❌ An error occurred: {e}{Colors.ENDC}")
            print("Please check the model's response and ensure your local LLM server is running.")


if __name__ == "__main__":
    main()


