from pathlib import Path
from urllib.parse import quote
from dotenv import dotenv_values

source = dotenv_values('../.env')
required = ('POSTGRES_PASSWORD', 'JWT_SECRET', 'ENCRYPTION_KEY')
if any(not source.get(key) for key in required):
    raise SystemExit('请先在根目录运行 scripts/init_env.py')
user = quote(source.get('POSTGRES_USER') or 'webhooks', safe='')
password = quote(source['POSTGRES_PASSWORD'], safe='')
name = quote(source.get('POSTGRES_DB') or 'webhooks', safe='')
port = source.get('POSTGRES_PORT') or '5432'
url = f'postgresql+asyncpg://{user}:{password}@127.0.0.1:{port}/{name}'
values = {
    'DATABASE_URL': url,
    'JWT_SECRET': source['JWT_SECRET'],
    'ENCRYPTION_KEY': source['ENCRYPTION_KEY'],
    'PUBLIC_BASE_URL': 'http://localhost:5173',
    'LLM_ALLOWED_HOSTS': source.get('LLM_ALLOWED_HOSTS') or 'api.openai.com',
    'ALLOW_HTTP_LLM': source.get('ALLOW_HTTP_LLM') or 'false',
    'ADMIN_USERNAME': source.get('ADMIN_USERNAME') or 'admin',
    'ADMIN_PASSWORD': source.get('ADMIN_PASSWORD') or 'Admin#123.',
}
path = Path('.env')
with path.open('x', encoding='utf-8') as output:
    for key, value in values.items():
        value = value.replace('\\', '\\\\').replace("'", "\\'")
        output.write(f"{key}='{value}'\n")
path.chmod(0o600)
print('已创建 backend/.env；现有配置不会被覆盖。')