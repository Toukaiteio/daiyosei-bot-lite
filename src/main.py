import sys
import os

# Ensure the project root is in the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.bot.bot import run_bot

if __name__ == "__main__":
    run_bot()
