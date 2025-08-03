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

# デバッグ用のStreamlit状態
if 'debug_logs' not in st.session_state:
    st.session_state.debug_logs = []

def debug_log(message):
    """デバッグメッセージをStreamlitに表示"""
    st.session_state.debug_logs.append(message)
    print(message)  # ターミナルにも出力

# AI記事判定用エージェントを作成
try:
    debug_log("エージェント作成中...")
    debug_log("MCPクライアントからツールを取得中...")
    
    # MCPクライアントを起動してツールを取得
    with fetch_client:
        mcp_tools = fetch_client.list_tools_sync()
        debug_log(f"MCPツール一覧: {[t.name for t in mcp_tools]}")
    
    # MCPツールを直接エージェントに渡す
    agent = Agent(
        model="us.anthropic.claude-sonnet-4-20250514-v1:0",
        tools=mcp_tools,
        system_prompt="""
与えられたブログ記事がAI生成か否か、パーセンテージで判定してください。

fetchツールを使ってURLからコンテンツを取得し、以下の特徴からAI生成記事かどうかを判定してください：

AI生成記事の特徴:
- タイトルや見出しに半角コロンが含まれている
- 箇条書きを多用する
- 箇条書きの冒頭がマークダウン太字で、半角コロンが使われている
- 日本人からすると不自然な表現が多い。抽象名詞による体言止め、不自然な主語（〜によって〜された、等）
- 出典のドメイン表示がそのまま残っている

判定結果は以下の形式で回答してください：
- AI生成の可能性: 高い/中程度/低い
- 根拠: 具体的な理由を3つ挙げる
- 信頼度: パーセンテージで表示
"""
    )
    debug_log("エージェント作成完了")
except Exception as e:
    debug_log(f"エージェント作成エラー: {type(e).__name__}: {str(e)}")
    import traceback
    debug_log(f"エージェント作成スタックトレース: {traceback.format_exc()}")
    agent = None

# ページタイトルと入力欄を表示
st.title("AI記事チェッカー")
blog_url = st.text_input("チェックしたいブログ記事のURLを入力してください")

# 非同期ストリーミング処理
async def process_stream(blog_url, container):
    text_holder = container.empty()
    response = ""
    prompt = f"""fetchツールを使って以下のURLからコンテンツを取得し、AI生成記事かどうかを判定してください：{blog_url}"""
    
    debug_log(f"[DEBUG] process_stream開始: URL={blog_url}")
    
    try:
        # MCPクライアントをwith句で起動してからエージェントを呼び出し
        debug_log("[DEBUG] fetch_clientをwith句で起動...")
        with fetch_client:
            debug_log("[DEBUG] エージェントストリーミング開始...")
            # エージェントからのストリーミングレスポンスを処理    
            async for chunk in agent.stream_async(prompt):
                debug_log(f"[DEBUG] chunk受信: {type(chunk)}")
                if isinstance(chunk, dict):
                    event = chunk.get("event", {})
                    debug_log(f"[DEBUG] event keys: {event.keys() if event else 'no event'}")

                    # ツール実行を検出して表示
                    if "contentBlockStart" in event:
                        tool_use = event["contentBlockStart"].get("start", {}).get("toolUse", {})
                        tool_name = tool_use.get("name")
                        debug_log(f"[DEBUG] ツール実行開始: {tool_name}")
                        
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
                        debug_log(f"[DEBUG] テキスト追加: {len(text)}文字")

    except Exception as e:
        debug_log(f"[DEBUG] process_stream例外: {type(e).__name__}: {str(e)}")
        import traceback
        debug_log(f"[DEBUG] process_streamスタックトレース: {traceback.format_exc()}")
        container.error(f"エラーが発生しました: {str(e)}")

# デバッグログを表示
if st.session_state.debug_logs:
    with st.expander("デバッグログ", expanded=False):
        for log in st.session_state.debug_logs[-20:]:  # 最新20件を表示
            st.text(log)

# ボタンを押したら分析開始
if st.button("AI記事チェック"):
    if blog_url:
        # デバッグログをクリア
        st.session_state.debug_logs = []
        debug_log("=== AI記事チェック開始 ===")
        
        if agent is None:
            debug_log("エラー: エージェントが初期化されていません")
            st.error("エージェントの初期化に失敗しています。")
            st.stop()
        
        try:
            debug_log(f"入力URL: {blog_url}")
            debug_log("process_stream関数を呼び出し中...")
            
            with st.spinner("ブログ記事を分析中…"):
                container = st.container()
                debug_log("asyncio.run実行前")
                asyncio.run(process_stream(blog_url, container))
                debug_log("asyncio.run実行後")
                
        except Exception as e:
            debug_log(f"メイン処理でエラー: {type(e).__name__}: {str(e)}")
            import traceback
            debug_log(f"メインスタックトレース: {traceback.format_exc()}")
            st.error(f"処理中にエラーが発生しました: {str(e)}")
    else:
        st.warning("URLを入力してください")

# エージェント初期化確認
st.sidebar.write("### 初期化状況")
try:
    st.sidebar.write(f"エージェント: {agent is not None}")
    st.sidebar.write(f"MCPクライアント: {fetch_client is not None}")
    debug_log(f"サイドバー: エージェント={agent is not None}, MCP={fetch_client is not None}")
except Exception as e:
    st.sidebar.error(f"初期化エラー: {str(e)}")
    debug_log(f"初期化確認エラー: {str(e)}")