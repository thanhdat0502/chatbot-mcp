from mcp.server.fastmcp import FastMCP
from duckduckgo_search import DDGS

# Khởi tạo MCP Server tên là SearchMCP
mcp = FastMCP("SearchMCP")

@mcp.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """Tra cứu và tìm kiếm thông tin trên internet bằng DuckDuckGo."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return f"Không tìm thấy kết quả nào cho '{query}'."
            
            output = "Kết quả tìm kiếm:\n"
            for r in results:
                output += f"- Tiêu đề: {r.get('title')}\n  URL: {r.get('href')}\n  Trích dẫn: {r.get('body')}\n\n"
            return output
    except Exception as e:
        return f"Lỗi trong quá trình tìm kiếm: {str(e)}"

if __name__ == "__main__":
    # fastmcp.run() tự động lắng nghe qua chuẩn Stdio
    mcp.run()
