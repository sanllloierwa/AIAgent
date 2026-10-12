# tools.py
import json
import os
import re
from datetime import datetime
from typing import List, Tuple, Optional
from openai import OpenAI
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_REASONING_EFFORT,
    PEXELS_API_KEY
)
from research import research_topic, web_search, web_fetch, HAS_DDGS
from images import (
    search_image_combined, download_image,
    extract_image_keywords, collect_user_images, image_to_data_uri
)

deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

# Reveal.js CDN（jsdelivr 国内可访问）
REVEAL_CDN = "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0"

# Beamer 主题名 → Reveal.js 主题名（未知值原样透传）
REVEAL_THEME_MAP = {
    "default": "white",
    "madrid": "black",
    "berlin": "league",
    "copenhagen": "sky",
    "warsaw": "night",
    "singapore": "simple",
    "rochester": "serif",
    "annarbor": "moon",
    "antibes": "blood",
    "montpellier": "beige",
    "pittsburgh": "solarized",
}

# LaTeX 字号偏好 → CSS 像素字号
FONT_SIZE_MAP = {
    "10pt": "18px", "11pt": "20px", "12pt": "22px",
    "14pt": "24px", "17pt": "28px", "20pt": "32px",
}

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


# ---------- 步骤2：为单个section生成HTML幻灯片（自主决定帧数）----------
def _generate_section_html(section: dict, preferences: dict, sec_idx: int, total_sec: int, ppt_title: str, image_path: Optional[str] = None, research_brief: Optional[str] = None, user_images: Optional[List[dict]] = None) -> str:
    """为单个section生成 Reveal.js <section> 块，模型自主决定拆成几帧"""
    points_text = "\n".join([f"  {i+1}. {p}" for i, p in enumerate(section["points"])])

    research_section = ""
    if research_brief:
        research_section = f"""

📚 参考资料（使用其中的真实数据/案例来充实本节）：
{research_brief[:1200]}
"""

    image_instruction = ""
    if user_images:
        img_list = "\n".join([
            f"- {os.path.basename(img['path'])} -- {img['desc']}"
            for img in user_images
        ])
        image_instruction = f"""
用户提供的图片素材（请根据本节主题选择最匹配的1张，如都不匹配可不插入）：

{img_list}

使用方式：在想插入图片的位置，单独写一行占位符 `[IMG:文件名]`（例如 `[IMG:climate_data.jpg]`），程序会自动把它替换为真正的图片。
- **如果没有一张图片与本节内容相关，不要强行插入**"""

    prompt = f"""你是一个HTML/Reveal.js幻灯片专家。请为以下PPT中的**单独一节**生成 Reveal.js 的 <section> 幻灯片块。

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
3. **每帧内容适量**：一帧内最多放1-2个主题+展开说明，列表项最多6条。
4. 第一帧必须是节标题+本节概览：<h2>节标题</h2> + 3-5条简短提要的 <ul>。
5. 每帧结构：<section><h2>或<h3>帧标题</h3>...</section>，帧与帧之间换行分隔。
6. 适当使用 <strong> 和 <span class="alert"> 强调关键词，使用 <ul>/<ol> 组织要点，可用 <table> 展示对比数据。
7. **只输出该节的一系列 <section>...</section> 块**，不要输出 <!DOCTYPE html>、<html>、<head>、<body>、<script> 等外层结构。
8. 不要使用 ```html 代码块包裹，直接输出纯HTML代码。"""

    response = deepseek_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        reasoning_effort=DEEPSEEK_REASONING_EFFORT,
        extra_body={"thinking": {"type": "enabled"}}
    )
    html = response.choices[0].message.content.strip()
    html = re.sub(r"^```html?\n?|```$", "", html)

    # 后处理：替换用户图片占位符 [IMG:文件名] 为 base64 data URI
    if user_images:
        by_name = {os.path.basename(img["path"]): img["path"] for img in user_images}
        for name, path in by_name.items():
            data_uri = image_to_data_uri(path)
            if data_uri:
                html = re.sub(
                    rf"\[IMG:\s*{re.escape(name)}\s*\]",
                    f'<img src="{data_uri}" alt="{name}" style="max-width:60%;max-height:55%;border-radius:8px;">',
                    html
                )

    # 后处理：自动配图插入到第一节（概述帧）之后
    if image_path:
        data_uri = image_to_data_uri(image_path)
        if data_uri:
            image_slide = (
                f'\n<section>\n<h3>{section["title"]}</h3>\n'
                f'<img src="{data_uri}" alt="{section["title"]} 配图" style="max-width:65%;max-height:60%;border-radius:8px;">\n'
                f'</section>'
            )
            if "</section>" in html:
                html = html.replace("</section>", image_slide + "\n</section>", 1)
            else:
                html = html + image_slide

    return html


# ---------- 步骤3：合并所有section为完整 Reveal.js HTML 文档 ----------
def _merge_sections(ppt_title: str, sections_html: List[str], preferences: dict, section_titles: Optional[List[str]] = None) -> str:
    """将所有section的HTML合并为完整的 Reveal.js 幻灯片文档"""
    theme = preferences.get('ppt_theme', 'default')
    font_size = preferences.get('font_size', '11pt')
    include_toc = preferences.get('include_toc', True)

    theme_name = REVEAL_THEME_MAP.get(theme.lower(), theme)
    font_px = FONT_SIZE_MAP.get(font_size, "20px")

    toc_block = ""
    if include_toc and section_titles:
        toc_items = "\n".join(f"<li>{t}</li>" for t in section_titles)
        toc_block = f"""<section>
<h2>目录</h2>
<ul>
{toc_items}
</ul>
</section>

"""

    title_slide = f"""<section>
<h1>{ppt_title}</h1>
<p class="meta">AI Agent 生成 · {datetime.now().strftime('%Y年%m月%d日')}</p>
</section>

{toc_block}"""

    body = "\n\n".join(sections_html)

    document = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{ppt_title}</title>
<link rel="stylesheet" href="{REVEAL_CDN}/dist/reveal.css">
<link rel="stylesheet" href="{REVEAL_CDN}/dist/theme/{theme_name}.css">
<style>
:root {{
  --base-font-size: {font_px};
}}
.reveal {{
  font-size: var(--base-font-size);
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
}}
.reveal h1, .reveal h2, .reveal h3 {{
  font-weight: 700;
}}
.reveal .alert {{
  color: #e74c3c;
  font-weight: 700;
}}
.reveal .meta {{
  color: #888;
  font-size: 0.6em;
}}
.reveal img {{
  max-width: 80%;
  max-height: 60vh;
  margin: 0 auto;
  display: block;
}}
.reveal table {{
  margin: 0 auto;
  border-collapse: collapse;
  font-size: 0.75em;
}}
.reveal th, .reveal td {{
  border: 1px solid #999;
  padding: 0.4em 0.8em;
}}
.reveal ul, .reveal ol {{
  text-align: left;
  display: inline-block;
}}
.reveal li {{
  margin: 0.35em 0;
  line-height: 1.5;
}}
</style>
</head>
<body>
<div class="reveal">
<div class="slides">

{title_slide}

{body}

</div>
</div>
<script src="{REVEAL_CDN}/dist/reveal.js"></script>
<script>
Reveal.initialize({{
  hash: true,
  slideNumber: 'c/t',
  transition: 'slide',
  progress: true,
  controls: true,
  width: 1280,
  height: 720
}});
</script>
</body>
</html>"""

    return document


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

    # 收集图片：用户图片 + 自动搜索
    image_source = preferences.get("image_source", "both")
    section_images = {}     # 自动搜索的图片 {section_index: local_path}
    user_images = []        # 用户提供的图片 [{path, desc}, ...]

    if image_source in ("user", "both"):
        user_images = collect_user_images()
        if user_images:
            print(f"\n📁 检测到 {len(user_images)} 张用户图片：")
            for img in user_images:
                print(f"   - {os.path.basename(img['path'])}: {img['desc']}")
        elif image_source == "user":
            print(f"\n📁 user_images/ 目录为空，无用户图片可用")
            print("   提示：将图片放入 user_images/ 目录，并编辑 descriptions.txt 添加描述")

    pexels_available = PEXELS_API_KEY and PEXELS_API_KEY != "YOUR_PEXELS_API_KEY"
    if image_source in ("auto", "both") and pexels_available:
        print(f"\n🔑 正在为各节提取英文搜索关键词...")
        section_keywords = extract_image_keywords(ppt_title, sections)

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
    elif image_source == "auto" and not pexels_available:
        print(f"\n⚠️  未配置 Pexels API Key，跳过图片搜索。")

    # 步骤2：逐节生成（注入研究简报和图片）
    print(f"\n📝 步骤 2/3：正在逐节生成详细内容...")
    sections_html = []
    for i, section in enumerate(sections):
        n_points = len(section["points"])
        has_img = "🖼️" if (i in section_images or user_images) else ""
        print(f"  生成第 {i+1}/{len(sections)} 节: {section['title']}（{n_points} 个要点）{has_img}...")
        image_path = section_images.get(i)
        html = _generate_section_html(section, preferences, i + 1, len(sections), ppt_title,
                                       image_path, research_brief, user_images)
        sections_html.append(html)

    # 步骤3：合并
    print(f"\n🔗 步骤 3/3：正在合并所有章节...")
    final_html = _merge_sections(
        ppt_title, sections_html, preferences,
        section_titles=[s["title"] for s in sections]
    )
    print(f"✅ PPT 生成完成！共 {len(sections)} 节。")

    return final_html


# ---------- 讲义生成 ----------
def generate_handout_from_outline(outline: str, preferences: dict) -> str:
    prompt = f"""你是一个HTML文档排版专家。请根据以下讲座/讲义纲要和用户偏好，生成完整的 HTML 讲义文档。

用户偏好：
- 详细程度：{preferences.get('handout_detail', 'medium')}
- 字体大小：{preferences.get('font_size', '11pt')}

纲要内容（Markdown 格式）：
{outline}

要求：
1. 输出完整 HTML 文档（从 <!DOCTYPE html> 到 </html>），lang="zh-CN"，<meta charset="UTF-8">。
2. 在 <head> 内联 <style> 实现 article 排版：内容列最大宽度 800px 居中、中文字体（"Microsoft YaHei", "PingFang SC", sans-serif）、行高 1.8、标题分级样式、列表和表格样式。
3. 讲义包括主标题（<h1>）、作者"AI Agent 生成"、日期（<p class="meta">）。
4. 根据纲要组织章节（<h2>）和子节（<h3>），使用 <ul>/<ol>/<p>/<table> 呈现内容。
5. 详细程度为 brief 时只保留核心条目；medium 时加入简单说明；full 时加入详细解释和示例。
6. 不要使用 ```html 代码块包裹，直接输出纯HTML代码。
"""
    response = deepseek_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    html = response.choices[0].message.content
    html = re.sub(r"^```html?\n?|```$", "", html.strip())
    return html


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
