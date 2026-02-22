Project Agent Instructions: Master-Trader Project Migration and Setup
Agent Name: Master-Trader-Setup-Agent
Model Target: Gemini CLI (Internal API)
Execution Context: Local Project Root Directory (Must contain the .git directory)

1. Project Initialization and Migration
The primary goal of this phase is to establish a new remote GitHub repository, named master-trader, and push the current, locally version-controlled project to it.
Task 1.1: Verify and Configure Git (Prerequisite)
Action: Ensure the project is properly staged and committed locally.
Command: git status
Expected Outcome: Clean working tree (optional: run git commit -am "Initial commit before Codespace migration" if needed).
Task 1.2: Create Remote GitHub Repository
Action: Use the GitHub CLI (gh) to create a new, private repository under the user's account.
Target Repository Name: master-trader
Description: "Automated Trading System (Python)"
Command:
gh repo create master-trader --private --description "Automated Trading System (Python)"


Task 1.3: Link Remote and Push Code
Action: Add the newly created remote repository and push all existing branches and tags from the local project.
Command 1 (Set Remote):
git remote add origin [https://github.com/$(gh](https://github.com/$(gh) api user --jq .login)/master-trader.git


Command 2 (Push All):
git push -u origin --all
git push -u origin --tags


Verification: Ensure all files (excluding the local, large venv folder, which should be listed in the project's .gitignore) are present on the remote master-trader repository.
2. Codespace Dev Container Configuration

The purpose of this phase is to create a configuration that allows the master-trader project to be spun up in a fully functional GitHub Codespace, addressing the large virtual environment by automating the dependency installation process.
Task 2.1: Ensure Dependency File Exists
Action: Verify that a requirements.txt file is present in the project root, verify if it contains all the necessary libraries for the project, listing all necessary Python packages.
Note: If requirements.txt is missing, instruct the agent to generate it first: pip freeze > requirements.txt (or equivalent for Poetry/Pipenv).
Task 2.2: Create the .devcontainer Directory
Action: Create the necessary directory structure for the Dev Container configuration.
Command:
mkdir -p .devcontainer

OBS: If you dont't know something aske for the user first for clarification instead of modifiying things blindly. 


