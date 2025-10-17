# Sidekick - Your Local AI Coding Agent

Sidekick is a command-line AI agent that brings a friendly, interactive development experience to your local machine. Powered by your own local LLM server (like LM Studio or vLLM), this agent can understand your requests, generate code, create and edit files, and even run tests to validate its own work.

# Features

Interactive Chat UI: A polished, chat-style interface for a fluid, back-and-forth conversation.

File System Operations: Can create and edit files directly in your project directory.

Automated Testing: Proposes and runs shell commands to test the code it generates.

Dynamic Model Switching: Use the /model command to fetch and switch between different models served by your backend on the fly.

Safety First: Requires user confirmation before making any file changes or running commands, with an "always allow" option for trusted sessions.

Flexible Configuration: Easily configure the API endpoint and default model via environment variables.

# How It Works

The agent uses a powerful system prompt to instruct a local language model to act as a software developer. When you give it a task, it doesn't just respond with text; it responds with a structured JSON "plan."

The Python script then parses this plan and executes the specified actions (like create_file or test), acting as the bridge between the AI's logic and your computer's file system.

# Installation

This project is packaged for easy installation with pip.

Clone the repository:

```
git clone https://github.com/krisclarkdev/sidekick.git
cd sidekick
```

Install the package:
Run the following command from the root of the project directory. This will install the script and all its dependencies as specified in pyproject.toml.

```
pip install .
```

This command handles the installation of:

```
langchain-openai
requests
prompt-toolkit
```

## Configuration

The agent is configured using environment variables. This is the recommended way to avoid hardcoding settings.

Set these variables in your shell's configuration file (~/.zshrc for Zsh on macOS, ~/.bashrc for Bash on Linux/WSL).

The URL of your OpenAI-compatible server (e.g., LM Studio, vLLM)

```
export AI_AGENT_API_BASE="http://localhost:1234/v1"
```

The specific model identifier your server is using by default

```
export AI_AGENT_MODEL="TheBloke/DeepSeek-Coder-V2-Lite-Instruct-AWQ"
```

A dummy API key (required by the library but not used by local servers)

```
export AI_AGENT_API_KEY="dummy-key"
```

Important: Remember to reload your shell (source ~/.zshrc or source ~/.bashrc) or open a new terminal for these changes to take effect.

# Usage

Once installed, you can run the agent from anywhere in your terminal:

```
sidekick
```

This will launch the interactive chat session.

In-App Commands

```
/help: Displays the list of available commands.
/model: Fetches a list of available models from your server and allows you to switch the active model for the current session.
/exit or /quit: Ends the chat session.
```
