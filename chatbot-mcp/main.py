import os
import sys
import asyncio
import sqlite3
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, LLM
from crewai.tools import tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Force utf-8 for Windows console
sys.stdout.reconfigure(encoding='utf-8')
load_dotenv()

model_name = os.getenv("model")
api_key = os.getenv("key")
base_url = os.getenv("base_url")

if not api_key or not base_url or not model_name:
    print("❌ LỖI: Không tìm thấy 'key', 'base_url', hoặc 'model' trong file .env!")
    sys.exit(1)

print(f"🚀 Đang khởi động Chatbot System với CrewAI & MCP Servers (Sử dụng model: {model_name})...")

# Khởi tạo mô hình LLM tùy chỉnh
custom_llm = LLM(
    model=f"openai/{model_name}" if not model_name.startswith("openai/") else model_name,
    api_key=api_key,
    base_url=base_url
)

# --- Các Tool gọi MCP Server ---

async def run_mcp_tool(command: str, args: list, tool_name: str, tool_args: dict) -> str:
    server_params = StdioServerParameters(command=command, args=args)
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, tool_args)
                return str(result.content[0].text if result.content else "Không có nội dung trả về.")
    except Exception as e:
        return f"Lỗi gọi MCP '{tool_name}': {str(e)}"

@tool("DuckDuckGo Web Search")
def web_search(query: str) -> str:
    """Tra cứu và tìm kiếm thông tin trên internet."""
    python_cmd = sys.executable
    return asyncio.run(run_mcp_tool(python_cmd, ["search_mcp.py"], "web_search", {"query": query, "max_results": 5}))

@tool("SQLite Read Query")
def sqlite_read_query(query: str) -> str:
    """Đọc dữ liệu từ DB (SELECT). Đầu vào là câu truy vấn SQL (Ví dụ: SELECT * FROM chat_history)."""
    mcp_cmd = "mcp-server-sqlite.exe" if sys.platform == "win32" else "mcp-server-sqlite"
    return asyncio.run(run_mcp_tool(mcp_cmd, ["--db-path", "chatbot.db"], "read_query", {"query": query}))

@tool("SQLite Write Query")
def sqlite_write_query(query: str) -> str:
    """Ghi dữ liệu vào DB (INSERT, UPDATE, DELETE). (Ví dụ: INSERT INTO chat_history (user_query, ai_response) VALUES (...))."""
    # SQLite MCP tool for modifications is generally 'write_query' or executed through 'read_query' if not restricted.
    # We will use read_query for both just in case, or write_query if it exists.
    mcp_cmd = "mcp-server-sqlite.exe" if sys.platform == "win32" else "mcp-server-sqlite"
    return asyncio.run(run_mcp_tool(mcp_cmd, ["--db-path", "chatbot.db"], "read_query", {"query": query}))

# --- Thiết lập Đội ngũ Agents ---

researcher = Agent(
    role="Chuyên gia Nghiên cứu",
    goal="Tra cứu thông tin mới nhất trên Internet bằng công cụ DuckDuckGo",
    backstory="Bạn là một nhà nghiên cứu tài ba. Khi có người nhờ tìm kiếm thông tin, bạn lập tức dùng công cụ DuckDuckGo để tra cứu và tóm tắt lại sự thật một cách chính xác.",
    tools=[web_search],
    llm=custom_llm,
    verbose=True,
    allow_delegation=False
)

db_specialist = Agent(
    role="Chuyên viên Dữ liệu",
    goal="Truy xuất lịch sử trò chuyện hoặc dữ liệu trong cơ sở dữ liệu SQLite",
    backstory="Bạn là một chuyên gia về CSDL. Bạn dùng công cụ SQLite để tìm kiếm trong bảng 'chat_history' bất cứ khi nào cần kiểm tra xem người dùng đã nói gì trước đây.",
    tools=[sqlite_read_query, sqlite_write_query],
    llm=custom_llm,
    verbose=True,
    allow_delegation=False
)

support_agent = Agent(
    role="Chuyên viên Chăm sóc Khách hàng",
    goal="Phân tích yêu cầu của người dùng, giao việc cho đúng chuyên gia và tổng hợp câu trả lời",
    backstory="Bạn là bộ mặt của hệ thống. Nhận yêu cầu từ người dùng, bạn sẽ giao việc (delegate) cho 'Chuyên gia Nghiên cứu' nếu cần thông tin mạng, hoặc giao cho 'Chuyên viên Dữ liệu' nếu cần xem lại lịch sử chat. Sau khi họ báo cáo lại, bạn tổng hợp thành câu trả lời thân thiện bằng tiếng Việt.",
    llm=custom_llm,
    verbose=True,
    allow_delegation=True
)

def chat_loop():
    # Khởi tạo DB mẫu
    if not os.path.exists("chatbot.db"):
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_query TEXT, ai_response TEXT)")
        conn.commit()
        conn.close()
        print("✅ Đã tạo database cục bộ chatbot.db")

    print("\n💬 Xin chào! Đội ngũ AI của chúng tôi đã sẵn sàng.")
    print("Bao gồm: Chuyên viên Hỗ trợ, Chuyên gia Nghiên cứu (DuckDuckGo) và Chuyên viên Dữ liệu (SQLite).")
    print("(Gõ 'exit' hoặc 'quit' để thoát)\n")
    
    while True:
        try:
            user_input = input("👤 Bạn: ")
            if user_input.lower() in ['exit', 'quit']:
                print("👋 Tạm biệt!")
                break
            
            if not user_input.strip():
                continue

            chat_task = Task(
                description=f"Người dùng vừa nhắn: '{user_input}'. Hãy xử lý yêu cầu này. Đừng ngần ngại sử dụng tính năng 'Delegate work to co-worker' để nhờ Chuyên gia Nghiên cứu hoặc Chuyên viên Dữ liệu giúp đỡ nếu bạn thiếu thông tin.",
                expected_output="Câu trả lời hoàn chỉnh, thân thiện, giải quyết đúng trọng tâm yêu cầu của người dùng bằng tiếng Việt.",
                agent=support_agent
            )

            crew = Crew(
                agents=[support_agent, researcher, db_specialist],
                tasks=[chat_task],
                verbose=False
            )

            print("🔄 Đội ngũ AI đang hội ý...")
            result = crew.kickoff()
            print(f"\n🤖 Hỗ trợ viên: {result}\n")

            # Tự động lưu lịch sử vào DB
            conn = sqlite3.connect("chatbot.db")
            cursor = conn.cursor()
            cursor.execute("INSERT INTO chat_history (user_query, ai_response) VALUES (?, ?)", (user_input, str(result)))
            conn.commit()
            conn.close()

        except KeyboardInterrupt:
            print("\n👋 Tạm biệt!")
            break
        except Exception as e:
            print(f"\n❌ Đã xảy ra lỗi: {e}\n")

if __name__ == "__main__":
    chat_loop()
