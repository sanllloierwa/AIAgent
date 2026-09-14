# images.py - 图片相关功能：在线搜索、下载、关键词提取、用户图片收集
import json
import os
import re
import hashlib
import requests
from typing import List, Optional
from openai import OpenAI
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    PEXELS_API_KEY, PEXELS_API_URL, PIXABAY_API_KEY, PIXABAY_API_URL,
    USER_IMAGES_DIR
)

deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


# ---------- 在线图片搜索 ----------
def search_image(query: str, max_results: int = 3) -> List[str]:
    """Pexels API 图片搜索"""
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
    """Pixabay API 图片搜索（备选源）"""
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


# ---------- 图片下载 ----------
def download_image(url: str, save_dir: str = ".") -> Optional[str]:
    """下载图片到本地，返回 LaTeX 兼容的本地文件路径"""
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
        return filepath.replace('\\', '/')
    except Exception as e:
        print(f"   ⚠️ 图片下载失败: {e}")
        return None


# ---------- 图片关键词提取（LLM 为所有 section 生成英文搜索词）----------
def extract_image_keywords(ppt_title: str, sections: List[dict]) -> dict:
    """用 LLM 一次性为所有 section 生成英文图片搜索关键词"""
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


# ---------- 用户本地图片收集 ----------
def collect_user_images() -> List[dict]:
    """扫描 user_images/ 目录，读取 descriptions.txt，返回 [{path, desc}, ...]"""
    images_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), USER_IMAGES_DIR)
    if not os.path.isdir(images_dir):
        return []

    desc_map = {}
    desc_file = os.path.join(images_dir, "descriptions.txt")
    if os.path.exists(desc_file):
        with open(desc_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                parts = line.split(":", 1)
                if len(parts) == 2:
                    desc_map[parts[0].strip()] = parts[1].strip()

    valid_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".pdf"}
    result = []
    for fname in sorted(os.listdir(images_dir)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in valid_exts:
            continue
        full_path = os.path.join(images_dir, fname).replace("\\", "/")
        desc = desc_map.get(fname) or os.path.splitext(fname)[0]
        result.append({"path": full_path, "desc": desc})

    return result
