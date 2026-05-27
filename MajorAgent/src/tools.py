# tools.py
import json
import re
import requests
from typing import List, Tuple
from openai import OpenAI
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_REASONING_EFFORT,
    PEXELS_API_KEY, PEXELS_API_URL
)

deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

# ---------- 步骤1：生成PPT大纲 ----------
def generate_ppt_outline(requirement: str, preferences: dict) -> str:
    prompt = f"""你是一个资深的演示文稿设计专家。请根据以下需求，生成一份**内容足够详细和完整**的PPT大纲，这份大纲将直接决定最终PPT的质量。

用户偏好：
- 主题风格：{preferences.get('ppt_theme', 'default')}

需求内容：
{requirement}

要求：
1. 大纲必须包含至少4-6个大节（section），每个大节下包含3-6张幻灯片（frame）。
2. 每张幻灯片的要点必须是**完整的陈述句**，包含具体的概念、方法、数据或案例，不能只写空洞的标题词（如"定义"、"概述"）。
3. 内容结构需完整：引言/背景（为什么要讲这个）→ 核心内容（拆分多个section，层层递进）→ 案例/应用 → 总结/展望。
4. 每个要点写成一个完整的陈述句，像备课笔记一样具体。例如：不要写"- 监督学习"，要写"- 监督学习使用带有标签的训练数据，模型通过学习输入-输出映射关系来进行预测，典型算法包括线性回归和决策树"。
5. 使用以下严格格式输出（方便程序解析）：

# TITLE: [PPT总标题，简洁有力]

## SECTION: [第一节标题]
### FRAME: [幻灯片1标题]
- 要点1的完整陈述句（1-2句话，包含具体信息）
- 要点2的完整陈述句（1-2句话，包含具体信息）
- 要点3的完整陈述句（1-2句话，包含具体信息）

### FRAME: [幻灯片2标题]
- 要点1的完整陈述句
- 要点2的完整陈述句

## SECTION: [第二节标题]
### FRAME: [幻灯片标题]
- ...

6. 仅输出大纲，不要包含任何额外解释。"""

    response = deepseek_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        reasoning_effort=DEEPSEEK_REASONING_EFFORT,
        extra_body={"thinking": {"type": "enabled"}}
    )
    return response.choices[0].message.content.strip()


# ---------- 解析大纲为结构化数据 ----------
def _parse_outline(outline_text: str) -> Tuple[str, List[dict]]:
    """解析大纲文本，返回 (总标题, [{section_title, frames: [{title, points}]}, ...])"""
    lines = outline_text.strip().split('\n')

    title = ""
    sections = []
    current_section = None
    current_frame = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        title_match = re.match(r'^#\s*TITLE:\s*(.+)', line, re.IGNORECASE)
        section_match = re.match(r'^##\s*SECTION:\s*(.+)', line, re.IGNORECASE)
        frame_match = re.match(r'^###\s*FRAME:\s*(.+)', line, re.IGNORECASE)
        bullet_match = re.match(r'^[-*]\s+(.+)', line)

        if title_match:
            title = title_match.group(1).strip()
        elif section_match:
            current_frame = None
            current_section = {
                "title": section_match.group(1).strip(),
                "frames": []
            }
            sections.append(current_section)
        elif frame_match and current_section is not None:
            current_frame = {
                "title": frame_match.group(1).strip(),
                "points": []
            }
            current_section["frames"].append(current_frame)
        elif bullet_match and current_frame is not None:
            current_frame["points"].append(bullet_match.group(1).strip())

    return title, sections


# ---------- 步骤2：为单个section生成详细LaTeX ----------
def _generate_section_latex(section: dict, preferences: dict, sec_idx: int, total_sec: int, ppt_title: str) -> str:
    """为单个section生成Beamer LaTeX帧（不含preamble）"""
    frames_desc = []
    for j, frame in enumerate(section["frames"]):
        points_text = "\n".join([f"  - {p}" for p in frame["points"]])
        frames_desc.append(f"  幻灯片{j+1}: {frame['title']}\n{points_text}")

    section_desc = f"第{sec_idx}节: {section['title']}\n" + "\n".join(frames_desc)

    prompt = f"""你是一个LaTeX Beamer专家，擅长制作内容详尽、有实用价值的演示文稿。请为以下PPT中的**单独一节**生成Beamer LaTeX代码。

用户偏好：
- 主题：{preferences.get('ppt_theme', 'default')}
- 字体大小：{preferences.get('font_size', '11pt')}

PPT总标题：{ppt_title}
当前进度：第 {sec_idx}/{total_sec} 节

本节大纲：
{section_desc}

核心要求（非常重要）：
1. 为每一张幻灯片生成一个 \\begin{{frame}}...\\end{{frame}} 块。
2. **每个要点必须展开为3-5句的详细说明段落**，不能只写一句标题。使用 \\begin{{itemize}} 列出要点后，在每个 \\item 下方用段落文字展开说明。
3. 添加具体的数据、案例、或示例来支撑每个观点，让听众有实际收获。
4. 适当使用 \\textbf{{}}、\\alert{{}}、\\textcolor{{blue}}{{}} 等强调关键词。
5. 本节的第一张幻灯片应为节标题页 + 本节内容概览：\\section{{{section['title']}}}
6. 每张幻灯片的内容应该足够丰富，使得一个不了解该主题的听众也能看懂。
7. **只输出 \\section{{...}} 和一系列 \\begin{{frame}}...\\end{{frame}} 块**，不要包含 \\documentclass、\\begin{{document}}、\\end{{document}} 等文档结构代码。
8. 不要使用 ```latex 代码块包裹，直接输出纯LaTeX代码。"""

    response = deepseek_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        reasoning_effort=DEEPSEEK_REASONING_EFFORT,
        extra_body={"thinking": {"type": "enabled"}}
    )
    code = response.choices[0].message.content.strip()
    code = re.sub(r"^```latex\n?|```$", "", code)
    return code


# ---------- 步骤3：合并所有section为完整Beamer文档 ----------
def _merge_sections(ppt_title: str, sections_latex: List[str], preferences: dict) -> str:
    """将preamble和所有section的LaTeX合并为完整文档"""
    theme = preferences.get('ppt_theme', 'default')
    font_size = preferences.get('font_size', '11pt')
    include_toc = preferences.get('include_toc', True)

    # 处理主题：Madrid等主题名首字母大写
    theme_map = {
        "default": "default",
        "madrid": "Madrid",
        "berlin": "Berlin",
        "copenhagen": "Copenhagen",
        "warsaw": "Warsaw",
        "singapore": "Singapore",
        "rochester": "Rochester",
        "annarbor": "AnnArbor",
        "antibes": "Antibes",
        "montpellier": "Montpellier",
        "pittsburgh": "Pittsburgh",
    }
    theme_name = theme_map.get(theme.lower(), theme)

    toc_block = "\\tableofcontents\n\\newpage" if include_toc else ""

    preamble = f"""\\documentclass[{font_size}]{{beamer}}
\\usetheme{{{theme_name}}}
\\usepackage{{ctex}}
\\usepackage{{graphicx}}

\\title{{{ppt_title}}}
\\author{{AI Agent 生成}}
\\date{{\\today}}

\\begin{{document}}

\\maketitle

{toc_block}
"""

    body = "\n\n".join(sections_latex)

    ending = "\n\n\\end{document}"

    return preamble + "\n" + body + ending


# ---------- PPT生成流水线（步骤1+2+3）----------
def generate_ppt_pipeline(requirement: str, preferences: dict) -> str:
    """完整三步流水线：大纲 → 逐节生成 → 合并"""
    # 步骤1：生成大纲
    print("\n📋 步骤 1/3：正在生成详细大纲...")
    outline = generate_ppt_outline(requirement, preferences)
    print("=" * 50)
    print(outline)
    print("=" * 50)

    # 解析大纲
    ppt_title, sections = _parse_outline(outline)
    if not sections:
        return "错误：无法解析大纲，请重试。"

    print(f"\n✅ 解析出 {len(sections)} 个大节，共 {sum(len(s['frames']) for s in sections)} 张幻灯片")

    # 步骤2：逐节生成
    print(f"\n📝 步骤 2/3：正在逐节生成详细内容...")
    sections_latex = []
    for i, section in enumerate(sections):
        print(f"  生成第 {i+1}/{len(sections)} 节: {section['title']}（{len(section['frames'])} 帧）...")
        latex = _generate_section_latex(section, preferences, i + 1, len(sections), ppt_title)
        sections_latex.append(latex)

    # 步骤3：合并
    print(f"\n🔗 步骤 3/3：正在合并所有章节...")
    final_latex = _merge_sections(ppt_title, sections_latex, preferences)
    print(f"✅ PPT 生成完成！共 {len(sections)} 节、{sum(len(s['frames']) for s in sections)} 张幻灯片。")

    return final_latex


# ---------- 讲义生成 ----------
def generate_handout_from_outline(outline: str, preferences: dict) -> str:
    prompt = f"""你是一个 LaTeX 专家。请根据以下讲座/讲义纲要和用户偏好，生成完整的 LaTeX 讲义文档。

用户偏好：
- 详细程度：{preferences.get('handout_detail', 'medium')}
- 字体大小：{preferences.get('font_size', '11pt')}

纲要内容（Markdown 格式）：
{outline}

要求：
1. 输出纯 LaTeX 代码，使用 \\documentclass[11pt]{{article}} 或根据偏好调整。
2. 讲义应包括标题、作者（设为"AI Agent 生成"）、日期。
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
        """根据大纲生成完整PPT（逐节生成+合并）"""
        return generate_ppt_pipeline(outline, self.prefs)

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
            return "格式错误，请使用 key=value，例如 ppt_theme=Madrid"

    def search_image(self, query: str) -> str:
        urls = search_image(query, max_results=3)
        return json.dumps(urls)
