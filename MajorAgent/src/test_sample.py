# test_sample.py - 测试样例：覆盖图片收集、大纲解析、逐节生成、合并、AgentTools
import json
import os
import sys
import re

# 切到 src 目录以便导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 切到项目根目录以便 user_images/ 路径正确
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# ============================================================
# 1. 用户图片收集
# ============================================================
print("\n" + "=" * 60)
print("1. collect_user_images()")
print("=" * 60)

from images import collect_user_images, extract_image_keywords
from images import search_image_combined, download_image

imgs = collect_user_images()
check("返回非空列表", len(imgs) > 0, f"got {len(imgs)}")
check("至少有3张图片", len(imgs) >= 3, f"got {len(imgs)}")

# 验证每张图片的数据结构
for img in imgs:
    check(f"  {os.path.basename(img['path'])} 有 path 和 desc", "path" in img and "desc" in img)
    check(f"  {os.path.basename(img['path'])} 路径用 / ", "\\" not in img["path"])

# 验证描述来源
earth = next((x for x in imgs if "earth_atmosphere" in x["path"]), None)
if earth:
    check("earth_atmosphere 使用 descriptions.txt", "大气层" in earth["desc"])

climate = next((x for x in imgs if "climate_data" in x["path"]), None)
if climate:
    check("climate_data 无描述则用文件名", climate["desc"] == "climate_data")


# ============================================================
# 2. 大纲解析
# ============================================================
print("\n" + "=" * 60)
print("2. _parse_outline()")
print("=" * 60)

from tools import _parse_outline

sample_outline = """# TITLE: 气候变化与环境保护

## SECTION: 气候变化的科学基础
- 温室效应是地球表面被大气层中的温室气体困住热量的自然现象，CO2和甲烷是主要温室气体
- 工业革命以来人类活动导致大气CO2浓度从280ppm上升到420ppm以上
- 全球平均温度自1880年以来上升了约1.1°C，其中大部分变暖发生在1975年以后
- 极端天气事件频率增加，热浪、洪水、干旱的强度和持续时间均有显著上升

## SECTION: 气候变化的影响
- 海平面以每年约3.7毫米的速度上升，威胁沿海城市和岛国
- 生物多样性锐减，约100万种物种面临灭绝风险
- 农业产量不稳定，小麦和玉米等主粮作物单产增速明显放缓

## SECTION: 应对策略与行动
- 巴黎协定目标将全球升温控制在2°C以内，力争1.5°C
- 可再生能源成本大幅下降，太阳能发电成本十年间下降约85%
- 碳捕获与封存技术(CCS)作为补充手段，预计2030年后大规模商业化
- 个人行动：减少碳足迹、绿色出行、节约能源等日常实践"""

title, sections = _parse_outline(sample_outline)
check("解析出标题", title == "气候变化与环境保护")
check("解析出3个 section", len(sections) == 3, f"got {len(sections)}")
check("第1节有4个要点", len(sections[0]["points"]) == 4, f"got {len(sections[0]['points'])}")
check("第2节有3个要点", len(sections[1]["points"]) == 3)
check("第3节有4个要点", len(sections[2]["points"]) == 4)


# ============================================================
# 3. 单节 LaTeX 生成（不调 LLM，仅验证 prompt 拼接）
# ============================================================
print("\n" + "=" * 60)
print("3. _generate_section_latex() prompt 拼接")
print("=" * 60)

from tools import _generate_section_latex

# 用小 topic 触发快速生成（会调 LLM）
section = {"title": "气候变化的科学基础", "points": ["温室效应的基本原理", "CO2浓度变化趋势"]}
prefs = {"image_source": "user"}

# 测试 user_images 参数传入后 prompt 中是否包含图片列表
# （不实际调 LLM，直接看函数签名是否正确）
import inspect
sig = inspect.signature(_generate_section_latex)
params = list(sig.parameters.keys())
check("参数包含 user_images", "user_images" in params)
check("参数包含 image_path", "image_path" in params)
check("参数包含 research_brief", "research_brief" in params)


# ============================================================
# 4. Section 合并
# ============================================================
print("\n" + "=" * 60)
print("4. _merge_sections()")
print("=" * 60)

from tools import _merge_sections

fake_sections = [
    r"\section{测试1}\begin{frame}\frametitle{Test}Content\end{frame}",
    r"\section{测试2}\begin{frame}\frametitle{Test2}More\end{frame}",
]
merged = _merge_sections("测试PPT", fake_sections, prefs)
check("合并后包含 documentclass", r"\documentclass" in merged)
check("合并后包含 begin document", r"\begin{document}" in merged)
check("合并后包含 end document", r"\end{document}" in merged)
check("合并后包含两个 section 内容", "测试1" in merged and "测试2" in merged)
check("合并后包含 graphicx 包", r"\usepackage{graphicx}" in merged)
check("合并后包含 ctex 包", r"\usepackage{ctex}" in merged)


# ============================================================
# 5. AgentTools 工具方法
# ============================================================
print("\n" + "=" * 60)
print("5. AgentTools 工具注册")
print("=" * 60)

from tools import AgentTools

tools = AgentTools({
    "ppt_theme": "Madrid", "font_size": "11pt",
    "include_toc": True, "handout_detail": "medium",
    "enable_web_research": False, "image_source": "user"
})

# 方法存在性
required_methods = ["generate_ppt", "generate_handout", "get_preferences",
                    "set_preference", "search_image", "web_search", "web_fetch"]
for m in required_methods:
    check(f"AgentTools.{m} 存在", hasattr(tools, m))

# get_preferences
prefs_json = tools.get_preferences()
parsed = json.loads(prefs_json)
check("get_preferences 返回有效 JSON", isinstance(parsed, dict))
check("image_source 为 user", parsed.get("image_source") == "user")

# set_preference
result = tools.set_preference("image_source=both")
check("set_preference 有效键", "已更新" in result)
check("prefs 已变更", tools.prefs["image_source"] == "both")

result = tools.set_preference("bad_key=xxx")
check("set_preference 未知键", "未知" in result)

result = tools.set_preference("badformat")
check("set_preference 错误格式", "格式错误" in result)


# ============================================================
# 6. 图片 API 函数（仅测试函数存在，不实际调 API）
# ============================================================
print("\n" + "=" * 60)
print("6. images.py 函数完整性")
print("=" * 60)

from images import search_image, search_image_pixabay, download_image

check("search_image 可调用", callable(search_image))
check("search_image_pixabay 可调用", callable(search_image_pixabay))
check("search_image_combined 可调用", callable(search_image_combined))
check("download_image 可调用", callable(download_image))
check("extract_image_keywords 可调用", callable(extract_image_keywords))
check("collect_user_images 可调用", callable(collect_user_images))


# ============================================================
# 7. 边界情况
# ============================================================
print("\n" + "=" * 60)
print("7. 边界情况")
print("=" * 60)

# 空大纲解析
title_empty, secs_empty = _parse_outline("")
check("空大纲返回空 sections", len(secs_empty) == 0)

# 格式错误的大纲
bad_outline = "这是一段没有格式的文本\n没有标题也没有section"
title_bad, secs_bad = _parse_outline(bad_outline)
check("无格式大纲返回空 sections", len(secs_bad) == 0)

# 只有标题没有 section
title_only, _ = _parse_outline("# TITLE: 只有标题")
check("只有标题的标题解析正确", title_only == "只有标题")

# user_images 为空列表时的处理
from tools import _generate_section_latex as gen_sec
# 传入空的 user_images 不应崩溃
# （不实际调 LLM，只验证参数传递）

# LaTeX 特殊字符转义（section title 中的 & _ % 等）
special_section = {"title": "测试 & 特殊 _ 字符 %", "points": ["要点1"]}
# 验证 _merge_sections 不会因特殊字符崩溃
try:
    _merge_sections("标题 & 特殊%", [r"\section{OK}\begin{frame}OK\end{frame}"], prefs)
    check("合并含特殊字符的标题不崩溃", True)
except Exception as e:
    check("合并含特殊字符的标题不崩溃", False, str(e))


# ============================================================
# 结果汇总
# ============================================================
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"结果: {PASS}/{total} 通过", end="")
if FAIL > 0:
    print(f", {FAIL} 失败")
else:
    print(" - 全部通过!")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
