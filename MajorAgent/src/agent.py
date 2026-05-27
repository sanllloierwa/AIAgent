# agent.py
import re
import json
import subprocess
import os
import shutil
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
- generate_ppt: 【三步流水线】生成完整详细的PPT。输入：用户的原始需求描述（直接传入用户的话即可，工具内部自动完成"大纲生成→逐节展开→合并"三步）。输入越详细，生成的PPT越完整。
- generate_handout: 根据纲要生成讲义的LaTeX代码。输入：文本纲要。
- get_preferences: 查看当前偏好设置，无需输入。
- set_preference: 修改偏好，输入格式 'key=value'。
- search_image: 根据关键词搜索图片，输入为关键词（字符串），返回图片URL列表（JSON格式）。

工作流程建议：
1. 当用户要求生成PPT时，直接将用户的完整需求传给 generate_ppt 工具。
2. generate_ppt 会自动先展示生成的大纲，然后逐节生成详细内容，最后合并为完整PPT。
3. 生成完成后，向用户简要说明结果（不需要重复输出LaTeX代码，工具已自动保存）。

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


def _find_latex_compiler() -> str:
    """查找可用的 LaTeX 编译器，优先 xelatex（原生Unicode/中文支持），其次 pdflatex"""
    miktex_bin = os.path.expandvars(r'%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64')
    system_miktex = r'C:\Program Files\MiKTeX\miktex\bin\x64'

    for compiler in ['xelatex', 'pdflatex']:
        if shutil.which(compiler):
            return compiler
        for base in [miktex_bin, system_miktex]:
            exe = os.path.join(base, f'{compiler}.exe')
            if os.path.exists(exe):
                return exe
    return 'xelatex'


def save_and_compile(latex_code: str, username: str) -> str:
    """保存 LaTeX 代码到 .tex 文件并尝试编译为 PDF"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    tex_filename = f"{username}_output_{timestamp}.tex"
    with open(tex_filename, "w", encoding='utf-8') as f:
        f.write(latex_code)
    print(f"📄 LaTeX 代码已保存至 {tex_filename}")

    print("🔄 正在尝试将 LaTeX 编译为 PDF ...")
    compiler = _find_latex_compiler()
    print(f"   使用编译器: {compiler}")
    try:
        result = subprocess.run(
            [compiler, '-interaction=nonstopmode', '-output-directory',
             os.path.dirname(tex_filename) or '.', tex_filename],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            subprocess.run(
                [compiler, '-interaction=nonstopmode', '-output-directory',
                 os.path.dirname(tex_filename) or '.', tex_filename],
                capture_output=True, text=True, timeout=60
            )
        base_name = os.path.splitext(tex_filename)[0]
        pdf_path = f"{base_name}.pdf"
        if os.path.exists(pdf_path):
            print(f"✅ 已生成可演示的 PDF 文件: {pdf_path}")
            print("   你可以直接打开该 PDF 文件进行演示。")
            return tex_filename
        else:
            log_path = f"{base_name}.log"
            print(f"⚠️ 编译失败，请查看日志 {log_path}")
            print(f"   请手动编译 .tex 文件以获得 PDF: {compiler} {tex_filename}")
            return tex_filename
    except FileNotFoundError:
        print("⚠️ 未找到 LaTeX 编译器。请安装 MiKTeX 或 TeX Live。")
        return tex_filename
    except subprocess.TimeoutExpired:
        print("⚠️ 编译超时，请手动编译。")
        return tex_filename
    except Exception as e:
        print(f"⚠️ 编译异常: {e}")
        return tex_filename


def run_agent(username: str, user_info: dict, tools, update_prefs_callback, first_question: str = None):
    prefs = user_info["preferences"]
    tool_funcs = {
        "generate_ppt": tools.generate_ppt,
        "generate_handout": tools.generate_handout,
        "get_preferences": tools.get_preferences,
        "set_preference": tools.set_preference,
        "search_image": tools.search_image,
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

        # 解析 Action（在 Final Answer 之前解析，因为工具结果要先拿到）
        action_match = re.search(r"Action:\s*(\w+)", llm_output)
        input_match = re.search(r"Action Input:\s*(.+)", llm_output)
        tool_name = "unknown"
        tool_input = ""

        if action_match and input_match:
            tool_name = action_match.group(1)
            tool_input = input_match.group(1).strip().strip('"')
            if tool_name in tool_funcs:
                observation = tool_funcs[tool_name](tool_input)
                # 如果工具返回了 LaTeX 代码，立即保存（不等 Final Answer）
                if isinstance(observation, str) and observation.startswith(r"\documentclass"):
                    save_and_compile(observation, username)
                    obs_lines = observation.count('\n')
                    observation = f"[LaTeX文档已生成并保存，共{obs_lines}行]"
                elif isinstance(observation, str):
                    # 截断长文本观察
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

        # 若修改了偏好，回调持久化
        if tool_name == "set_preference" and "偏好已更新" in observation:
            update_prefs_callback(username, tools.prefs)

        # Final Answer 处理（放在 Action 处理之后）
        if "Final Answer:" in llm_output:
            final = llm_output.split("Final Answer:")[-1].strip()
            print(f"✅ 最终结果已输出。")
            # 只在工具还没有保存过文件时，才从 Final Answer 中提取 LaTeX 保存
            code_match = re.search(r"```latex\n(.*?)\n```", final, re.DOTALL)
            if code_match and not (action_match and input_match and tool_name == "generate_ppt"):
                latex_code = code_match.group(1)
                save_and_compile(latex_code, username)
            break

    # 询问是否继续
    again = input("\n是否继续其他操作？(y/n): ")
    if again.lower() == 'y':
        run_agent(username, user_info, tools, update_prefs_callback)
