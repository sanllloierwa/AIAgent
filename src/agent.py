# agent.py
import re
import json
import webbrowser
from datetime import datetime
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_REASONING_EFFORT, MAX_AGENT_ROUNDS

deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)

REACT_PROMPT = """你是一个智能助手，擅长生成PPT和讲义。当前用户偏好如下：
{preferences}

你可以使用以下工具：
- generate_ppt: 【联网研究+自动配图】生成完整详细的PPT。输入：用户的原始需求描述。工具内部自动完成"联网搜索→资料整理→大纲生成→搜索配图→逐节展开→合并"全流程。生成的PPT基于真实网络资料，数据可靠。
- generate_handout: 根据纲要生成讲义的HTML代码。输入：文本纲要。
- web_search: 联网搜索资料，输入为搜索关键词（字符串），返回标题、URL、摘要列表（JSON格式）。
- web_fetch: 抓取指定网页的正文内容，输入为URL（字符串），返回提取的文本。
- search_image: 根据关键词搜索并下载图片到本地，输入为关键词（字符串）。
- get_preferences: 查看当前偏好设置，无需输入。
- set_preference: 修改偏好，输入格式 'key=value'。可用键：ppt_theme, font_size, include_toc, handout_detail, enable_web_research, image_source（auto=自动搜图, user=仅用user_images/中的图, both=两者都用）。

工作流程建议：
1. 如果用户要求生成PPT，直接将用户的完整需求传给 generate_ppt 工具，联网研究和配图全自动完成。
2. 如果需要更深入研究，先用 web_search 搜索，再用 web_fetch 抓取重点页面，然后将收集的资料合并后传给 generate_ppt。
3. 生成完成后，向用户简要说明结果。

请严格遵循以下格式：

Question: 用户的问题
Thought: 你的思考
Action: 工具名称
Action Input: 工具的输入（字符串）
Observation: 工具返回的结果
...（可重复）
Thought: 我现在知道最终答案了
Final Answer: 对用户的最终回复

开始！

Question: {question}
{history}
Thought:
"""


def save_html_file(html_code: str, username: str) -> str:
    """保存 HTML 代码到 .html 文件并自动在浏览器中打开"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    html_filename = f"{username}_output_{timestamp}.html"
    with open(html_filename, "w", encoding='utf-8') as f:
        f.write(html_code)
    print(f"📄 HTML 文件已保存至 {html_filename}")

    try:
        webbrowser.open(html_filename)
        print("🖥️  已在浏览器中打开，使用方向键/空格翻页。")
    except Exception as e:
        print(f"⚠️ 自动打开浏览器失败: {e}，请手动打开该文件。")
    return html_filename


def run_agent(username: str, user_info: dict, tools, update_prefs_callback, first_question: str = None):
    prefs = user_info["preferences"]
    tool_funcs = {
        "generate_ppt": tools.generate_ppt,
        "generate_handout": tools.generate_handout,
        "get_preferences": tools.get_preferences,
        "set_preference": tools.set_preference,
        "search_image": tools.search_image,
        "web_search": tools.web_search,
        "web_fetch": tools.web_fetch,
    }

    print(f"\n欢迎 {username}！当前偏好：{prefs}\n")
    history = ""
    question = first_question or input("请输入您的需求：")

    for _ in range(MAX_AGENT_ROUNDS):
        prompt = REACT_PROMPT.format(
            preferences=json.dumps(prefs, indent=2),
            question=question,
            history=history
        )
        response = deepseek_client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            reasoning_effort=DEEPSEEK_REASONING_EFFORT,
            extra_body={"thinking": {"type": "enabled"}}
        )
        llm_output = response.choices[0].message.content
        print(f"\n🤖 Agent: {llm_output}\n")

        # 解析 Action
        action_match = re.search(r"Action:\s*(\w+)", llm_output)
        input_match = re.search(r"Action Input:\s*(.+)", llm_output)
        tool_name = "unknown"
        tool_input = ""

        if action_match and input_match:
            tool_name = action_match.group(1)
            tool_input = input_match.group(1).strip().strip('"')
            if tool_name in tool_funcs:
                observation = tool_funcs[tool_name](tool_input)
                # 如果工具返回了完整 HTML 文档，立即保存
                if isinstance(observation, str) and observation.strip().lower().startswith(("<!doctype html", "<html")):
                    save_html_file(observation, username)
                    obs_lines = observation.count('\n')
                    observation = f"[HTML文档已生成并保存，共{obs_lines}行]"
                elif isinstance(observation, str):
                    if len(observation) > 500:
                        observation = observation[:500] + "..."
                else:
                    observation = str(observation)
            else:
                observation = f"错误：未知工具 {tool_name}"
        else:
            observation = "格式错误，请输出正确的 Action 和 Action Input"

        history += f"Thought: {llm_output.split('Thought:')[-1].split('Action:')[0]}\n"
        history += f"Action: {tool_name}\nAction Input: {tool_input}\nObservation: {observation}\n"

        if tool_name == "set_preference" and "偏好已更新" in observation:
            update_prefs_callback(username, tools.prefs)

        # Final Answer 处理（放在 Action 之后，确保本轮工具已执行）
        if "Final Answer:" in llm_output:
            final = llm_output.split("Final Answer:")[-1].strip()
            print(f"✅ 最终结果已输出。")
            # 只在工具还没保存过文件时，才从 Final Answer 中提取 HTML
            code_match = re.search(r"```html\n(.*?)\n```", final, re.DOTALL)
            if code_match and not (action_match and input_match and tool_name == "generate_ppt"):
                html_code = code_match.group(1)
                save_html_file(html_code, username)
            break

    # 询问是否继续
    again = input("\n是否继续其他操作？(y/n): ")
    if again.lower() == 'y':
        run_agent(username, user_info, tools, update_prefs_callback)
