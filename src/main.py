# main.py
from user_manager import register, login, update_preferences
from tools import AgentTools
from agent import run_agent

def main():
    print("===== AI Agent 系统（支持PPT/讲义/图片搜索）=====")
    action = input("请选择：1-注册  2-登录 : ")
    if action == "1":
        username = input("用户名：")
        pwd = input("密码：")
        if register(username, pwd):
            print("注册成功！请登录。")
        else:
            print("用户已存在。")
        action = "2"

    if action == "2":
        username = input("用户名：")
        pwd = input("密码：")
        user = login(username, pwd)
        if not user:
            print("登录失败")
            return
        print("登录成功！")

        # 创建工具实例（注入用户偏好）
        tools = AgentTools(user["preferences"])
        # 运行 Agent，传入偏好更新回调
        run_agent(
            username=username,
            user_info=user,
            tools=tools,
            update_prefs_callback=update_preferences
        )

if __name__ == "__main__":
    main()