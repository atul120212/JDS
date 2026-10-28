import sys
from pathlib import Path

# Ensure root directory is on the Python path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from jd_collector.api import create_app

# Vercel looks for the `app` export
app = create_app(with_scheduler=False)
