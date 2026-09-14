# research.py - Web research module: search, fetch, extract, summarize
import json
import re
import requests
from typing import List, Dict, Optional
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

deepseek_client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

HAS_DDGS = False
DDGS = None
try:
    from ddgs import DDGS
    HAS_DDGS = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        HAS_DDGS = True
    except ImportError:
        pass

HAS_BS4 = False
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    pass


def web_search(query: str, max_results: int = 5) -> List[Dict]:
    """搜索网页，返回 [{title, url, snippet}, ...]"""
    if not HAS_DDGS:
        return [{"error": "请安装 duckduckgo_search: pip install duckduckgo_search"}]

    try:
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                })
            return results
    except Exception as e:
        return [{"error": str(e)}]


def web_fetch(url: str, max_chars: int = 3000) -> str:
    """Fetch and extract text content from a URL"""
    headers_list = [
        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
    ]

    for headers in headers_list:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()

            if HAS_BS4:
                soup = BeautifulSoup(resp.text, 'html.parser')
                for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                    tag.decompose()
                text = soup.get_text(separator='\n', strip=True)
            else:
                text = re.sub(r'<script[^>]*>.*?</script>', '', resp.text, flags=re.DOTALL)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text)

            text = re.sub(r'\n\s*\n', '\n\n', text)
            text = re.sub(r'[ \t]+', ' ', text)

            if len(text) > max_chars:
                text = text[:max_chars] + "..."

            return text.strip()
        except Exception:
            continue

    return "[Fetch failed: all attempts exhausted]"


def research_topic(topic: str, max_sources: int = 3) -> Optional[str]:
    """研究主题：搜索 → 抓取 → LLM摘要 → 返回研究简报"""
    if not HAS_DDGS:
        print("   ⚠️ 未安装 duckduckgo_search，跳过联网研究")
        return None

    print(f"\n[Web] Searching: {topic[:60]}...")

    search_results = web_search(topic, max_results=5)
    if not search_results or "error" in search_results[0]:
        print(f"   Search failed: {search_results[0].get('error', 'unknown') if search_results else 'no results'}")
        return None

    print(f"   Found {len(search_results)} pages")

    sources_text = []
    for i, result in enumerate(search_results[:max_sources]):
        title = result.get('title', '')[:60]
        print(f"   [{i+1}/{max_sources}] Fetching: {title}...")
        content = web_fetch(result['url'], max_chars=2500)
        if content and not content.startswith('['):
            sources_text.append(f"--- Source {i+1}: {result['title']}\nURL: {result['url']}\n{content}")

    if not sources_text:
        print("   Failed to fetch any page content")
        return None

    combined = "\n\n".join(sources_text)
    if len(combined) > 8000:
        combined = combined[:8000]

    prompt = f"""你是一个研究助理。请根据以下网络搜索资料，为主题"{topic}"的PPT制作提取关键参考信息。

资料内容：
{combined}

请提取并整理（中文输出）：
1. **核心概念**（3-5个，各1-2句解释）
2. **关键数据/案例**（至少3个，包含具体数字或事实）
3. **重要时间线/里程碑**（如涉及）
4. **不同观点/争议**（如有）

只输出整理后的内容，总字数控制在500字以内。"""

    response = deepseek_client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1000
    )

    brief = response.choices[0].message.content.strip()
    print(f"   Research brief ready ({len(brief)} chars)")
    return brief
