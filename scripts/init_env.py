"""Create local Compose secrets without overwriting an existing .env."""
import base64
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
path = root / ".env"
content = (root / ".env.example").read_text()
content = content.replace("replace-with-random-password", secrets.token_hex(24))
content = content.replace("replace-with-at-least-32-random-characters", secrets.token_hex(32))
content = content.replace("replace-with-fernet-key", base64.urlsafe_b64encode(os.urandom(32)).decode())
with path.open("x") as output:
    output.write(content)
path.chmod(0o600)
print("Created .env. Set PUBLIC_BASE_URL and LLM_ALLOWED_HOSTS before deployment.")
