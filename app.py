# 必要なライブラリをインポート
import os, asyncio
import streamlit as st
from strands import Agent
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

# AI記事判定用エージェントを作成
with fetch_client:
    mcp_tools = fetch_client.list_tools_sync()

agent = Agent(
    model="us.anthropic.claude-opus-4-20250514-v1:0",
    tools=mcp_tools,
    system_prompt="""
与えられたブログ記事がAI生成か否か、パーセンテージで判定してください。

AI生成記事の特徴:
- タイトルや見出しに半角コロンが含まれている
- タイトルや見出しの先頭に絵文字が含まれている
- タイトルに「完全ガイド」や「徹底解説」といった表現含まれる
- 箇条書きを多用する
- 箇条書きの冒頭がマークダウン太字で、半角コロンが使われている
- 日本人からすると不自然な表現が多い。抽象名詞による体言止め、不自然な主語（〜によって〜された、等）
- o3に見られる、分かりやすく説明するための端的だが違和感のある表現「つまり〜」が多い
- 出典のドメイン表示がそのまま残っている

出力の最後に「投稿者の表現がたまたまAI生成の特徴に一致しているだけの可能性もあります。
このアプリによる判定結果を公開したり、他人に共有することは控えてください」と添えて。
"""
)

# ページタイトルと入力欄を表示
st.title("AI記事チェッカー")
blog_url = st.text_input("チェックしたいブログ記事のURLを入力してください")

# 非同期ストリーミング処理
async def process_stream(blog_url, container):
    text_holder = container.empty()
    response = ""
    prompt = f"fetchツールを使って以下のURLからコンテンツを取得し、AI生成記事かどうかを判定してください：{blog_url}"
    
    with fetch_client:
        async for chunk in agent.stream_async(prompt):
            if isinstance(chunk, dict):
                event = chunk.get("event", {})

                # ツール実行を検出して表示
                if "contentBlockStart" in event:
                    tool_use = event["contentBlockStart"].get("start", {}).get("toolUse", {})
                    tool_name = tool_use.get("name")
                    
                    if response:
                        text_holder.markdown(response)
                        response = ""

                    container.info(f"🔧 {tool_name} ツールを実行中…")
                    text_holder = container.empty()
                
                # テキストを抽出してリアルタイム表示
                if text := chunk.get("data"):
                    response += text
                    text_holder.markdown(response)

# ボタンを押したら分析開始
if st.button("AI記事チェック"):
    if blog_url:
        with st.spinner("ブログ記事を分析中…"):
            container = st.container()
            asyncio.run(process_stream(blog_url, container))
    else:
        st.warning("URLを入力してください")