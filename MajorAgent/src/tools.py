# tools.py
import json
import re
import requests
from typing import List
from openai import OpenAI              # 仍然使用 OpenAI Python SDK[reference:11]
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_REASONING_EFFORT,
    PEXELS_API_KEY, PEXELS_API_URL
)

# 初始化 DeepSeek 客户端 (因为接口兼容，可直接使用 OpenAI 的客户端)[reference:12]
deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

# ---------- 基础工具：生成 PPT / 讲义 ----------
def generate_ppt_from_outline(outline: str, preferences: dict) -> str:
    prompt = f"""你是一个 LaTeX 专家。请根据以下 PPT 纲要和用户偏好，生成完整的 Beamer 文档代码。

用户偏好：
- 主题：{preferences.get('ppt_theme', 'default')}
- 字体大小：{preferences.get('font_size', '11pt')}
- 包含目录：{preferences.get('include_toc', True)}

纲要内容（Markdown 格式）：
{outline}

要求：
1. 输出纯 LaTeX 代码，可直接保存为 .tex 文件并用 pdflatex 编译。
2. 使用 \\documentclass[presentation]{{beamer}}，根据偏好选择主题。
3. 根据纲要自动生成节（section）和帧（frame）。
4. 如果用户偏好要求包含目录，在 \\begin{{document}} 后添加 \\tableofcontents。
5. 仅输出 LaTeX 代码，不要包含额外解释。
"""
    response = deepseek_client.chat.completions.create(
        model=DEEPSEEK_MODEL,                                   # 使用 DeepSeek 模型
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        reasoning_effort=DEEPSEEK_REASONING_EFFORT,            # 传入思考模式参数[reference:13]
        extra_body={"thinking": {"type": "enabled"}}           # 显式启用思考模式[reference:14]
    )
    latex_code = response.choices[0].message.content
    latex_code = re.sub(r"^```latex\n?|```$", "", latex_code.strip())
    return latex_code

def generate_handout_from_outline(outline: str, preferences: dict) -> str:
    prompt = f"""你是一个 LaTeX 专家。请根据以下讲座/讲义纲要和用户偏好，生成完整的 LaTeX 讲义文档。

用户偏好：
- 详细程度：{preferences.get('handout_detail', 'medium')}
- 字体大小：{preferences.get('font_size', '11pt')}

纲要内容（Markdown 格式）：
{outline}

要求：
1. 输出纯 LaTeX 代码，使用 \\documentclass[11pt]{{article}} 或根据偏好调整。
2. 讲义应包括标题、作者（设为“AI Agent 生成”）、日期。
3. 根据纲要组织章节（\\section）和子节（\\subsection）。
4. 详细程度为 brief 时只保留核心条目；medium 时加入简单说明；full 时加入详细解释和示例。
5. 仅输出 LaTeX 代码。
"""
    response = deepseek_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    latex_code = response.choices[0].message.content
    latex_code = re.sub(r"^```latex\n?|```$", "", latex_code.strip())
    return latex_code

# ---------- 图片搜索工具（Pexels API）----------
def search_image(query: str, max_results: int = 3) -> List[str]:
    """返回图片URL列表"""
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": max_results}
    try:
        response = requests.get(PEXELS_API_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        return [photo['src']['original'] for photo in data.get('photos', [])]
    except Exception as e:
        print(f"图片搜索失败: {e}")
        return []

# ---------- 工具包装类（注入偏好）----------
class AgentTools:
    def __init__(self, preferences: dict):
        self.prefs = preferences

    def generate_ppt(self, outline: str) -> str:
        return generate_ppt_from_outline(outline, self.prefs)

    def generate_handout(self, outline: str) -> str:
        return generate_handout_from_outline(outline, self.prefs)

    def get_preferences(self) -> str:
        return json.dumps(self.prefs, indent=2)

    def set_preference(self, key_value: str) -> str:
        try:
            key, value = key_value.split("=", 1)
            key, value = key.strip(), value.strip()
            if key in self.prefs:
                self.prefs[key] = value
                return f"偏好已更新：{key} = {value}"
            else:
                return f"未知的偏好键：{key}。可用键：{list(self.prefs.keys())}"
        except Exception:
            return "格式错误，请使用 key=value，例如 ppt_theme=dark"

    def search_image(self, query: str) -> str:
        """搜索图片，返回JSON格式的URL列表"""
        urls = search_image(query, max_results=3)
        return json.dumps(urls)