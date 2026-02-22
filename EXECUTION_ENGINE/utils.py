import os

def load_env_file():
    """
    Manually parses the .env file in the project root and sets 
    environment variables if they aren't already set.
    """
    # Look for .env in the project root (parent of EXECUTION_ENGINE)
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(base_path, ".env")
    
    if not os.path.exists(env_path):
        print(f"Warning: .env file not found at {env_path}")
        return

    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): continue
            if '=' in line:
                key, value = line.split('=', 1)
                # Strip quotes if present
                value = value.strip().strip("'").strip('"')
                os.environ[key.strip()] = value
                
    # Debug print (masked)
    # user = os.environ.get('WEBULL_USER', 'Not Set')
    # print(f"Loaded .env. User: {user[:3]}***")
