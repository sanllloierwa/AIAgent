# config.py
import os

# DeepSeek API 配置 (OpenAI兼容模式)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-28685b485a2c46ad8ec0373217b70730")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"           # DeepSeek官方端点[reference:4][reference:5]
DEEPSEEK_MODEL = "deepseek-v4-pro"                      # 主力专业模型[reference:6]
# DEEPSEEK_MODEL = "deepseek-v4-flash"                  # 可选的轻量模型

# DeepSeek 思考模式强度：'low', 'medium', 'high'[reference:7][reference:8]
DEEPSEEK_REASONING_EFFORT = "medium"

# 以下配置保持不变
USER_DB_FILE = "users.json"
MAX_AGENT_ROUNDS = 5
# 图片搜索配置
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "YOUR_PEXELS_API_KEY")
PEXELS_API_URL = "https://api.pexels.com/v1/search"