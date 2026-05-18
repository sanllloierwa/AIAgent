# agent.py
import re
import json
from openai import OpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, DEEPSEEK_REASONING_EFFORT, MAX_AGENT_ROUNDS

# 初始化 DeepSeek 客户端
deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL
)
REACT_PROMPT = """你是一个能生成PPT和讲义的智能助手。当前用户偏好如下：
{preferences}

你可以使用以下工具：
- generate_ppt: 根据纲要生成PPT的LaTeX代码。输入：文本纲要（支持Markdown格式）。
- generate_handout: 根据纲要生成讲义的LaTeX代码。输入：文本纲要。
- get_preferences: 查看当前偏好设置，无需输入。
- set_preference: 修改偏好，输入格式 'key=value'。
- search_image: 根据关键词搜索图片，输入为关键词（字符串），返回图片URL列表（JSON格式）。

请严格遵循以下格式：

Question: 用户的问题
Thought: 你的思考
Action: 工具名称
Action Input: 工具的输入（字符串）
Observation: 工具返回的结果
...（可重复）
Thought: 我现在知道最终答案了
Final Answer: 对用户的最终回复（通常应包含生成的LaTeX代码或确认信息）

开始！

Question: {question}
{history}
Thought: 
"""

def run_agent(username: str, user_info: dict, tools, update_prefs_callback, first_question: str = None):
    """
    运行 Agent 多轮对话。
    - tools: AgentTools 实例
    - update_prefs_callback: 函数，用于持久化偏好更新
    """
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
            reasoning_effort=DEEPSEEK_REASONING_EFFORT,        # 传入思考模式参数[reference:15]
            extra_body={"thinking": {"type": "enabled"}}       # 显式启用思考模式[reference:16]
        )
        llm_output = response.choices[0].message.content
        print(f"\n🤖 Agent: {llm_output}\n")

        if "Final Answer:" in llm_output:
            final = llm_output.split("Final Answer:")[-1].strip()
            print(f"✅ 最终结果已输出。")
            # 提取 LaTeX 代码块并保存
            code_match = re.search(r"```latex\n(.*?)\n```", final, re.DOTALL)
            if code_match:
                latex_code = code_match.group(1)
                from datetime import datetime
                filename = f"{username}_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tex"
                with open(filename, "w") as f:
                    f.write(latex_code)
                print(f"📄 LaTeX 代码已保存至 {filename}")
            break

        # 解析 Action
        action_match = re.search(r"Action:\s*(\w+)", llm_output)
        input_match = re.search(r"Action Input:\s*(.+)", llm_output)
        if action_match and input_match:
            tool_name = action_match.group(1)
            tool_input = input_match.group(1).strip().strip('"')
            if tool_name in tool_funcs:
                observation = tool_funcs[tool_name](tool_input)
            else:
                observation = f"错误：未知工具 {tool_name}"
        else:
            observation = "格式错误，请输出正确的 Action 和 Action Input"

        history += f"Thought: {llm_output.split('Thought:')[-1].split('Action:')[0]}\n"
        history += f"Action: {tool_name}\nAction Input: {tool_input}\nObservation: {observation}\n"

        # 若修改了偏好，回调持久化
        if tool_name == "set_preference" and "偏好已更新" in observation:
            update_prefs_callback(username, tools.prefs)

    # 询问是否继续
    again = input("\n是否继续其他操作？(y/n): ")
    if again.lower() == 'y':
        run_agent(username, user_info, tools, update_prefs_callback)