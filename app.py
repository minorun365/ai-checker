# 必要なライブラリをインポート
import os, asyncio
import streamlit as st
from strands import Agent, tool
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

# Streamlitシークレットを環境変数に設定
os.environ['AWS_ACCESS_KEY_ID'] = st.secrets['AWS_ACCESS_KEY_ID']
os.environ['AWS_SECRET_ACCESS_KEY'] = st.secrets['AWS_SECRET_ACCESS_KEY']
os.environ['AWS_DEFAULT_REGION'] = st.secrets['AWS_DEFAULT_REGION']

# fetch MCPクライアントを初期化
fetch_client = MCPClient(
    lambda: stdio_client(StdioServerParameters(
        command="uvx", 
        args=["mcp-server-fetch", "--ignore-robots-txt"]
    ))
)

# fetch機能をツールとして定義
@tool
async def fetch_url_content(url: str) -> str:
    """URLからコンテンツを取得する"""
    print(f"[DEBUG] fetch_url_content呼び出し: URL={url}")
    try:
        # MCPクライアントをwith句で起動してからツールを呼び出し
        print("[DEBUG] MCPクライアントを起動中...")
        with fetch_client:
            print("[DEBUG] ツール一覧を取得中...")
            tools = fetch_client.list_tools_sync()
            print(f"[DEBUG] 利用可能なツール: {[t.name for t in tools]}")
            
            fetch_tool = None
            for tool_info in tools:
                if tool_info.name == "fetch":
                    fetch_tool = tool_info
                    break
            
            if fetch_tool:
                print(f"[DEBUG] fetchツール実行中: URL={url}")
                result = await fetch_client.call_tool_async(fetch_tool.name, {"url": url})
                print(f"[DEBUG] 結果: {type(result)}, keys: {result.keys() if isinstance(result, dict) else 'not dict'}")
                content = result.get("content", "コンテンツの取得に失敗しました") if isinstance(result, dict) else str(result)
                print(f"[DEBUG] コンテンツ長: {len(content)} 文字")
                return content
            else:
                print("[DEBUG] fetchツールが見つかりません")
                return "fetchツールが見つかりません"
    except Exception as e:
        print(f"[DEBUG] 例外発生: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"[DEBUG] スタックトレース: {traceback.format_exc()}")
        return f"エラー: {str(e)}"

# AI記事判定用エージェントを作成
agent = Agent(
    model="us.anthropic.claude-sonnet-4-20250514-v1:0",
    tools=[fetch_url_content],
    system_prompt="""
与えられたブログ記事がAI生成か否か、パーセンテージで判定してください。

AI生成記事の特徴は以下です。
- タイトルや見出しに半角コロンが含まれている
- 箇条書きを多用する
- 箇条書きの冒頭がマークダウン太字で、半角コロンが使われている
- 日本人からすると不自然な表現が多い。抽象名詞による体言止め、不自然な主語（〜によって〜された、等）
- 出典のドメイン表示がそのまま残っている
"""
)

# ページタイトルと入力欄を表示
st.title("AI記事チェッカー")
blog_url = st.text_input("チェックしたいブログ記事のURLを入力してください")

# 非同期ストリーミング処理
async def process_stream(blog_url, container):
    text_holder = container.empty()
    response = ""
    prompt = f"""以下のURLの記事をfetch_url_contentツールで取得し、
AI生成されたものかどうかを判定してください：{blog_url}"""
    
    print(f"[DEBUG] process_stream開始: URL={blog_url}")
    
    try:
        # MCPクライアントをwith句で起動してからエージェントを呼び出し
        print("[DEBUG] fetch_clientをwith句で起動...")
        with fetch_client:
            print("[DEBUG] エージェントストリーミング開始...")
            # エージェントからのストリーミングレスポンスを処理    
            async for chunk in agent.stream_async(prompt):
                print(f"[DEBUG] chunk受信: {type(chunk)}")
                if isinstance(chunk, dict):
                    event = chunk.get("event", {})
                    print(f"[DEBUG] event keys: {event.keys() if event else 'no event'}")

                    # ツール実行を検出して表示
                    if "contentBlockStart" in event:
                        tool_use = event["contentBlockStart"].get("start", {}).get("toolUse", {})
                        tool_name = tool_use.get("name")
                        print(f"[DEBUG] ツール実行開始: {tool_name}")
                        
                        # バッファをクリア
                        if response:
                            text_holder.markdown(response)
                            response = ""

                        # ツール実行のメッセージを表示
                        container.info(f"🔧 {tool_name} ツールを実行中…")
                        text_holder = container.empty()
                    
                    # テキストを抽出してリアルタイム表示
                    if text := chunk.get("data"):
                        response += text
                        text_holder.markdown(response)
                        print(f"[DEBUG] テキスト追加: {len(text)}文字")

    except Exception as e:
        print(f"[DEBUG] process_stream例外: {type(e).__name__}: {str(e)}")
        import traceback
        print(f"[DEBUG] process_streamスタックトレース: {traceback.format_exc()}")
        container.error(f"エラーが発生しました: {str(e)}")

# ボタンを押したら分析開始
if st.button("AI記事チェック"):
    if blog_url:
        with st.spinner("ブログ記事を分析中…"):
            container = st.container()
            asyncio.run(process_stream(blog_url, container))
    else:
        st.warning("URLを入力してください")