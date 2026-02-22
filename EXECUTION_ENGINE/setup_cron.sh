#!/bin/bash

# Get Project Path
PROJECT_DIR=$(pwd)
PYTHON_EXEC="$PROJECT_DIR/venv/bin/python3"

echo "--- Generating Crontab Entries ---"
echo "Copy the lines below and paste them into 'crontab -e'"
echo "-----------------------------------------------------"

# 1. 6:00 AM: Run Scanner & Ranker
echo "0 6 * * 1-5 cd $PROJECT_DIR && $PYTHON_EXEC -m EXECUTION_ENGINE.rank_live_signals >> $PROJECT_DIR/EXECUTION_ENGINE/cron_ranker.log 2>&1"

# 2. 9:35 AM: Run Auto Trader (Entry)
echo "35 9 * * 1-5 cd $PROJECT_DIR && $PYTHON_EXEC -m EXECUTION_ENGINE.auto_trader >> $PROJECT_DIR/EXECUTION_ENGINE/cron_trader.log 2>&1"

# 3. Every 5 Mins (9:40 - 15:55): Run Portfolio Manager (Exit)
echo "*/5 9-15 * * 1-5 cd $PROJECT_DIR && $PYTHON_EXEC -m EXECUTION_ENGINE.portfolio_manager >> $PROJECT_DIR/EXECUTION_ENGINE/cron_manager.log 2>&1"

# 4. 4:05 PM: Generate Daily Report
echo "5 16 * * 1-5 cd $PROJECT_DIR && $PYTHON_EXEC -m EXECUTION_ENGINE.investment_reporter >> $PROJECT_DIR/EXECUTION_ENGINE/cron_report.log 2>&1"

echo "-----------------------------------------------------"
echo "Done."
