# tools.py
import json
import os
import re
import hashlib
import requests
from typing import List, Tuple, Optional
from openai import OpenAI
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_REASONING_EFFORT,
    PEXELS_API_KEY, PEXELS_API_URL, PIXABAY_API_KEY, PIXABAY_API_URL
)
from research import research_topic, web_search, web_fetch, HAS_DDGS

deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

# ---------- 步骤1：生成PPT大纲（不预设帧，只列要点）----------
def generate_ppt_outline(requirement: str, preferences: dict, research_brief: Optional[str] = None) -> str:
    research_section = ""
    if research_brief:
        research_section = f"""

📚 **联网研究参考资料**（务必参考以下真实数据/案例）：
{research_brief}

"""

    prompt = f"""你是一个资深的演示文稿设计专家。请根据以下需求，生成一份**内容足够详细和完整**的PPT大纲。

用户偏好：
- 主题风格：{preferences.get('ppt_theme', 'default')}

需求内容：
{requirement}
{research_section}
要求：
1. 大纲必须包含至少4-6个大节（section），每个大节下列出4-8个核心要点。
2. 每个要点必须是**完整的陈述句**，包含具体的概念、方法、数据或案例。
3. {("如果有参考资料，务必引用其中的具体数据、案例和事实，而非凭空编造。" if research_brief else "")}内容结构需完整：引言/背景（为什么要讲这个）→ 核心内容（拆分多个section，层层递进）→ 案例/应用 → 总结/展望。
4. 要点像备课笔记一样具体。例如不要写"- 监督学习"，要写"- 监督学习使用带标签的训练数据，模型通过学习输入-输出映射关系来进行预测，典型算法包括线性回归和决策树"。
5. 使用以下严格格式输出（方便程序解析）：

# TITLE: [PPT总标题，简洁有力]

## SECTION: [第一节标题]
- 要点1的完整陈述句（1-2句话，包含具体信息）
- 要点2的完整陈述句（1-2句话，包含具体信息）
- 要点3的完整陈述句（1-2句话，包含具体信息）

## SECTION: [第二节标题]
- 要点1的完整陈述句
- 要点2的完整陈述句

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
    """解析大纲文本，返回 (总标题, [{title, points: [str, ...]}, ...])"""
    lines = outline_text.strip().split('\n')

    title = ""
    sections = []
    current_section = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        title_match = re.match(r'^#\s*TITLE:\s*(.+)', line, re.IGNORECASE)
        section_match = re.match(r'^##\s*SECTION:\s*(.+)', line, re.IGNORECASE)
        bullet_match = re.match(r'^[-*]\s+(.+)', line)

        if title_match:
            title = title_match.group(1).strip()
        elif section_match:
            current_section = {
                "title": section_match.group(1).strip(),
                "points": []
            }
            sections.append(current_section)
        elif bullet_match and current_section is not None:
            current_section["points"].append(bullet_match.group(1).strip())

    return title, sections


# ---------- 步骤2：为单个section生成详细LaTeX（自主决定帧数）----------
def _generate_section_latex(section: dict, preferences: dict, sec_idx: int, total_sec: int, ppt_title: str, image_path: Optional[str] = None, research_brief: Optional[str] = None) -> str:
    """为单个section生成Beamer LaTeX帧（不含preamble），模型自主决定拆成几帧"""
    points_text = "\n".join([f"  {i+1}. {p}" for i, p in enumerate(section["points"])])

    research_section = ""
    if research_brief:
        research_section = f"""

📚 参考资料（使用其中的真实数据/案例来充实本节）：
{research_brief[:1200]}
"""

    image_instruction = ""
    if image_path:
        image_instruction = f"""
图片素材：本节配有一张配图，路径为 `{image_path}`（路径必须使用正斜杠/，严禁使用反斜杠\\）。

使用原则：
- 如果图片能呼应本节主题，在概述帧之后插入图片帧（1帧即可）：
```
\\begin{{frame}}\\frametitle{{...}}
\\begin{{center}}
\\includegraphics[width=0.7\\textwidth]{{{image_path}}}
\\end{{center}}
\\end{{frame}}
```
- 插入图片后可加1帧简短解读，说明图片与本节的关联。
- **如果图片与本节内容完全无关，不要强行插入**——宁可不用也不要破坏专业性。"""

    prompt = f"""你是一个LaTeX Beamer专家。请为以下PPT中的**单独一节**生成Beamer LaTeX代码。

PPT总标题：{ppt_title}
当前进度：第 {sec_idx}/{total_sec} 节
本节标题：{section['title']}

本节需要覆盖的要点：
{points_text}
{research_section}
{image_instruction}

核心要求：
1. **内容要详细**：每个要点展开为3-5句的详细说明，添加具体案例、数据或示例。
2. **自主决定帧数**：根据内容量自行决定拆成几帧（通常3-8帧）。复杂要点可以独占一帧，简单要点可以合并。不要让任何一帧的内容溢出幻灯片。
3. **每帧内容适量**：一帧内最多放1-2个主题+展开说明。如果 \\item 的展开段落超过5行，说明该主题应该单独成帧。
4. 第一帧必须是节标题+本节概览：列出本节的几个子主题（3-5条简短提要）。
5. 使用 \\begin{{frame}}\\frametitle{{...}}...\\end{{frame}} 结构。
6. 适当使用 \\textbf{{}}、\\alert{{}} 强调关键词，使用 \\begin{{itemize}} 组织要点。
7. **只输出 \\section{{...}} 和一系列 \\begin{{frame}}...\\end{{frame}} 块**，不要包含 \\documentclass、\\begin{{document}}、\\end{{document}}。
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


# ---------- 图片关键词提取（LLM一次性为所有section生成英文搜索词）----------
def _extract_image_keywords(ppt_title: str, sections: List[dict]) -> dict:
    """用LLM为所有section提取英文图片搜索关键词（一次调用）"""
    sections_text = "\n".join([
        f"Section {i}: {s['title'][:60]}\n  Key concepts: {'; '.join(s['points'][:3])}"
        for i, s in enumerate(sections)
    ])

    prompt = f"""For each section of a Chinese presentation below, generate 2-3 short English keywords (1-3 words each) that would find relevant stock photos on Pexels.

Presentation topic: {ppt_title[:100]}

{sections_text}

IMPORTANT:
- Focus on concrete, visual nouns (e.g., "robot arm", "team collaboration", "computer code", "city skyline")
- Avoid abstract terms that don't photograph well (not "synergy", "optimization theory")
- Use common English terms that photographers tag their photos with

Return ONLY a valid JSON object:
{{"0": ["keyword1", "keyword2"], "1": ["keyword1", "keyword2"], ...}}
Map the section index to its keywords array.

JSON:"""

    response = deepseek_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=500
    )
    try:
        text = response.choices[0].message.content.strip()
        text = re.sub(r'^```json\s*|```$', '', text).strip()
        return json.loads(text)
    except (json.JSONDecodeError, KeyError, AttributeError):
        return {}


# ---------- PPT生成流水线（步骤1+2+3）----------
def generate_ppt_pipeline(requirement: str, preferences: dict) -> str:
    """完整流水线：联网研究 → 大纲 → 关键词提取 → 配图 → 逐节生成 → 合并"""
    # 步骤0：联网研究（如启用）
    research_brief = None
    if preferences.get('enable_web_research', True) and HAS_DDGS:
        research_brief = research_topic(requirement, max_sources=3)

    # 步骤1：生成大纲（注入研究简报）
    print("\n📋 步骤 1/3：正在生成详细大纲...")
    outline = generate_ppt_outline(requirement, preferences, research_brief)
    print("=" * 50)
    print(outline)
    print("=" * 50)

    # 解析大纲
    ppt_title, sections = _parse_outline(outline)
    if not sections:
        return "错误：无法解析大纲，请重试。"

    total_points = sum(len(s["points"]) for s in sections)
    print(f"\n✅ 解析出 {len(sections)} 个小节，共 {total_points} 个要点（实际帧数由模型自主决定）")

    # 搜索并下载配图（用LLM提取英文关键词）
    section_images = {}
    pexels_available = PEXELS_API_KEY and PEXELS_API_KEY != "YOUR_PEXELS_API_KEY"
    if pexels_available:
        print(f"\n🔑 正在为各节提取英文搜索关键词...")
        section_keywords = _extract_image_keywords(ppt_title, sections)

        print(f"🖼️  正在搜索配图...")
        for i, section in enumerate(sections):
            keywords = section_keywords.get(str(i), [])
            if not keywords:
                keywords = [section['title'][:40]]

            found = False
            for kw in keywords[:3]:
                urls = search_image_combined(kw, max_results=1)
                if urls:
                    local_path = download_image(urls[0], save_dir=".")
                    if local_path:
                        section_images[i] = local_path
                        print(f"   [{i+1}/{len(sections)}] {section['title'][:30]}... -> '{kw}' -> 已下载")
                        found = True
                        break

            if not found:
                print(f"   [{i+1}/{len(sections)}] {section['title'][:30]}... -> 未找到相关图片，跳过")
    else:
        print(f"\n⚠️  未配置 Pexels API Key，跳过图片搜索。")

    # 步骤2：逐节生成（注入研究简报）
    print(f"\n📝 步骤 2/3：正在逐节生成详细内容...")
    sections_latex = []
    for i, section in enumerate(sections):
        n_points = len(section["points"])
        has_img = "🖼️" if i in section_images else ""
        print(f"  生成第 {i+1}/{len(sections)} 节: {section['title']}（{n_points} 个要点）{has_img}...")
        image_path = section_images.get(i)
        latex = _generate_section_latex(section, preferences, i + 1, len(sections), ppt_title, image_path, research_brief)
        sections_latex.append(latex)

    # 步骤3：合并
    print(f"\n🔗 步骤 3/3：正在合并所有章节...")
    final_latex = _merge_sections(ppt_title, sections_latex, preferences)
    print(f"✅ PPT 生成完成！共 {len(sections)} 节。")

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
        print(f"   Pexels 搜索失败: {e}")
        return []


def search_image_pixabay(query: str, max_results: int = 3) -> List[str]:
    """Pixabay 图片搜索（备选源）"""
    if not PIXABAY_API_KEY:
        return []
    params = {"key": PIXABAY_API_KEY, "q": query, "per_page": max_results}
    try:
        response = requests.get(PIXABAY_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        return [hit['largeImageURL'] for hit in data.get('hits', [])]
    except Exception as e:
        print(f"   Pixabay 搜索失败: {e}")
        return []


def search_image_combined(query: str, max_results: int = 3) -> List[str]:
    """组合搜索：先 Pexels，无结果则 Pixabay"""
    results = search_image(query, max_results)
    if not results:
        results = search_image_pixabay(query, max_results)
    return results


def download_image(url: str, save_dir: str = ".") -> Optional[str]:
    """下载图片到本地，返回本地文件路径"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        ext = url.split('.')[-1].split('?')[0] or 'jpg'
        if ext not in ('jpg', 'jpeg', 'png', 'gif', 'bmp'):
            ext = 'jpg'
        filename = hashlib.md5(url.encode()).hexdigest()[:12] + '.' + ext
        filepath = os.path.join(save_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(response.content)
        return filepath.replace('\\', '/')  # LaTeX 必须使用正斜杠
    except Exception as e:
        print(f"   ⚠️ 图片下载失败: {e}")
        return None


# ---------- 工具包装类（注入偏好）----------
class AgentTools:
    def __init__(self, preferences: dict):
        self.prefs = preferences

    def generate_ppt(self, outline: str) -> str:
        """根据需求生成完整PPT（三步流水线）"""
        return generate_ppt_pipeline(outline, self.prefs)

    def generate_handout(self, outline: str) -> str:
        return generate_handout_from_outline(outline, self.prefs)

    def get_preferences(self, _: str = "") -> str:
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
        urls = search_image_combined(query, max_results=3)
        if not urls:
            return json.dumps({"status": "no_results", "urls": []})
        local_paths = []
        for url in urls:
            local = download_image(url, save_dir=".")
            if local:
                local_paths.append(local)
        return json.dumps({"status": "ok", "urls": urls, "local_paths": local_paths})

    def web_search(self, query: str) -> str:
        """联网搜索，返回结果列表"""
        results = web_search(query, max_results=5)
        if not results:
            return json.dumps({"status": "no_results"})
        if "error" in results[0]:
            return json.dumps({"status": "error", "message": results[0]["error"]})
        return json.dumps(results, ensure_ascii=False)

    def web_fetch(self, url: str) -> str:
        """抓取网页正文"""
        content = web_fetch(url.strip(), max_chars=3000)
        return content if content else "[获取失败]"
