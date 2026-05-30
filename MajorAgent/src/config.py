# config.py
import os

# 尝试从 .env 文件加载环境变量
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

_load_dotenv()

# DeepSeek API 配置 (OpenAI兼容模式)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-0bdcb03edb274eb88680ec6e06044311")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"           # DeepSeek官方端点
DEEPSEEK_MODEL = "deepseek-v4-pro"                      # 主力专业模型
# DEEPSEEK_MODEL = "deepseek-v4-flash"                  # 可选的轻量模型

# DeepSeek 思考模式强度：'low', 'medium', 'high'
DEEPSEEK_REASONING_EFFORT = "medium"

# 以下配置保持不变
USER_DB_FILE = "users.json"
MAX_AGENT_ROUNDS = 5
# 图片搜索配置（在 https://www.pexels.com/api/ 免费注册获取 Key）
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "bWhTXghJr43Ed2Kot9FlcO90wXZsx2sIdnflSlnDKHuqdvOhJw95FK45")
PEXELS_API_URL = "https://api.pexels.com/v1/search"