import json
import os
import sys
import time
from pathlib import Path

import requests

# ---- 設定(ここを調整) ----
WINDOW_MIN = 60        # 何分間の値幅を見るか
THRESHOLD_YEN = 0.1    # この値幅(円)以上動いたら通知
COOLDOWN_MIN = 15      # 一度通知したら何分間は再通知しないか
# --------------------------

STATE_FILE = Path("state/state.json")
LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]


def fetch_rate() -> float:
    r = requests.get(
        "https://api.twelvedata.com/price",
        params={"symbol": "USD/JPY", "apikey": os.environ["TWELVE_DATA_API_KEY"]},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    if "price" not in data:
        raise RuntimeError(f"APIからの応答が想定外です: {data}")
    return float(data["price"])


def send_line(text: str) -> None:
    res = requests.post(
        "https://api.line.me/v2/bot/message/broadcast",
        headers={"Authorization": f"Bearer {LINE_TOKEN}"},
        json={"messages": [{"type": "text", "text": text}]},
        timeout=10,
    )
    print(f"LINE応答: {res.status_code} {res.text}")
    res.raise_for_status()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"history": [], "last_notified": 0.0}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def main() -> None:
    state = load_state()
    now = time.time()
    is_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    try:
        rate = fetch_rate()
    except Exception as e:
        print(f"レート取得に失敗: {e}")
        sys.exit(1)

    history = [h for h in state["history"] if h[0] >= now - WINDOW_MIN * 60]
    history.append([now, rate])

    rates = [r for _, r in history]
    width = max(rates) - min(rates)
    print(f"現在 {rate:.3f}円 / 直近{WINDOW_MIN}分の値幅 {width:.2f}円")

    if is_manual:
        send_line(f"テスト通知です(手動実行)\n現在: {rate:.3f}円")
        print("LINEにテスト通知を送信しました")

    if width >= THRESHOLD_YEN and now - state["last_notified"] >= COOLDOWN_MIN * 60:
        direction = "円安方向" if rate > history[0][1] else "円高方向"
        send_line(
            f"ドル円が急変動です({direction})\n"
            f"現在: {rate:.3f}円\n"
            f"直近{WINDOW_MIN}分の値幅: {width:.2f}円"
        )
        state["last_notified"] = now
        print("LINEに急変動の通知を送信しました")
    else:
        print("急変動の通知条件には達していません")

    state["history"] = history
    save_state(state)


if __name__ == "__main__":
    main()
