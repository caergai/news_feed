import subprocess
import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)

def push_reports():
    """Pushes the reports directory to GitHub."""
    # Get the project root directory (where git_ops.py resides)
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    try:
        # 1. Stage the reports folder and feed.json
        subprocess.run(["git", "add", "docs/"], check=True, cwd=project_root)
        
        # 2. Commit the changes
        date_str = datetime.now().strftime("%Y-%m-%d")
        commit_msg = f"Daily update: General News - {date_str}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True, cwd=project_root)
        
        # 3. Push to remote
        subprocess.run(["git", "push", "origin", "main"], check=True, cwd=project_root)
        
        log.info("Successfully pushed reports to GitHub.")
        return True
    except subprocess.CalledProcessError as e:
        log.error("Git operation failed: %s", e)
        return False
    except Exception as e:
        log.error("Unexpected error during git push: %s", e)
        return False
