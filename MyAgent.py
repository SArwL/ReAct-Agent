"""MyAgent —— 程序入口：实例化 ReActAgent 并运行。"""

from ReActAgent import ReActAgent


def main():
    agent = ReActAgent()
    task = input("请输入你的问题：")
    answer = agent.run(task)
    print("=== 最终答案 ===")
    print(answer)


if __name__ == "__main__":
    main()
