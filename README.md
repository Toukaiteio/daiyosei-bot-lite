# Daiyosei Bot Lite

Daiyosei Bot Lite is a Python-based chat bot designed for roleplay and companionship. It utilizes LLMs (OpenAI, Gemini) for conversation and features memory retention, autonomous web search, and vision capabilities. It connects to message providers via WebSocket (OneBot V11).

## Requirements

- Python 3.10+
- Conda
- Git

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Toukaiteio/daiyosei-bot-lite.git
   cd daiyosei-bot-lite
   ```

2. Create and activate the Conda environment:
   ```bash
   conda env create -f environment.yml
   conda activate daiyosei
   ```

3. Install Python dependencies (if needed):
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. Create the configuration file:
   ```bash
   cp .env.example .env
   ```
   *On Windows use `copy .env.example .env`*

2. Edit `.env` to configure your settings:
   - **LLM_PROVIDERS**: Configure your LLM endpoints (OpenAI/Gemini), API keys, and capabilities (vision/search).
   - **WS_HOST / WS_PORT**: Set the WebSocket address for your message provider (e.g., NapCat, OneBot).
   - **BOT_NAME**: Set the bot's persona name.

## Usage

Start the bot:
```bash
python -m src.main
```

Ensure your OneBot/NapCat message provider is running and configured to connect to the bot's WebSocket address (default: `ws://127.0.0.1:6199`).
