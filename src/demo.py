import requests
import os
from typing import List

# ========== 配置 ==========
API_KEY = "bWhTXghJr43Ed2Kot9FlcO90wXZsx2sIdnflSlnDKHuqdvOhJw95FK45"          # 替换为你的真实 API Key
SEARCH_QUERY = "sunset"  # 搜索关键词（建议用英文）
MAX_RESULTS = 3                          # 下载图片数量
DOWNLOAD_FOLDER = "pexels_downloads"     # 保存目录

# API 端点
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# ========== 搜索图片 ==========
def search_images(query: str, per_page: int = 10) -> List[dict]:
    """搜索图片，返回图片信息列表（每个包含 id, url, photographer 等）"""
    headers = {"Authorization": API_KEY}
    params = {"query": query, "per_page": per_page}
    response = requests.get(PEXELS_SEARCH_URL, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("photos", [])

# ========== 下载图片 ==========
def download_image(url: str, save_path: str):
    """下载图片到本地"""
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"已保存: {save_path}")

# ========== 主程序 ==========
def main():
    # 创建下载目录
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

    print(f"🔍 正在搜索关键词: {SEARCH_QUERY}")
    photos = search_images(SEARCH_QUERY, per_page=MAX_RESULTS)

    if not photos:
        print("❌ 未找到任何图片，请尝试其他关键词。")
        return

    print(f"✅ 找到 {len(photos)} 张图片，开始下载：\n")
    for idx, photo in enumerate(photos):
        # 获取图片信息
        img_id = photo["id"]
        photographer = photo["photographer"]
        img_url = photo["src"]["original"]   # 原始尺寸
        print(f"📸 图片 {idx+1}: ID={img_id}, 摄影师={photographer}")
        print(f"   URL: {img_url}")

        # 下载
        ext = img_url.split('.')[-1].split('?')[0]
        filename = f"{SEARCH_QUERY.replace(' ', '_')}_{img_id}.{ext}"
        save_path = os.path.join(DOWNLOAD_FOLDER, filename)
        try:
            download_image(img_url, save_path)
        except Exception as e:
            print(f"   ❌ 下载失败: {e}")
        print()

    print("🎉 下载完成！")

if __name__ == "__main__":
    main()