import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---- 設定(ここを調整) ----
WINDOW_MIN = 60        # 何分間の値幅を見るか
THRESHOLD_YEN = 0.1   # この値幅(円)以上動いたら通知
COOLDOWN_MIN = 30      # 一度通知したら何分間は再通知しないか
# --------------------------

STATE_FILE = Path("state/state.json")
LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
API_KEY = os.environ["TWELVE_DATA_API_KEY"]


def fetch_candles() -> list:
    """過去WINDOW_MIN分の1分足を、新しい順で返す。"""
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": "USD/JPY",
            "interval": "1min",
            "outputsize": WINDOW_MIN,
            "timezone": "UTC",
            "apikey": API_KEY,
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    if "values" not in data:
        raise RuntimeError(f"APIからの応答が想定外です: {data}")
    return data["values"]


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
    return {"last_notified": 0.0}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def main() -> None:
    state = load_state()
    now = time.time()
    is_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    try:
        candles = fetch_candles()
    except Exception as e:
        print(f"レート取得に失敗: {e}")
        sys.exit(1)

    rate = float(candles[0]["close"])
    latest = datetime.strptime(candles[0]["datetime"], "%Y-%m-%d %H:%M:%S")
    latest = latest.replace(tzinfo=timezone.utc)
    age_min = (datetime.now(timezone.utc) - latest).total_seconds() / 60
    print(f"現在 {rate:.3f}円(最新データは{age_min:.0f}分前)")

    if is_manual:
        send_line(f"テスト通知です(手動実行)\n現在: {rate:.3f}円")
        print("LINEにテスト通知を送信しました")

    if age_min > 20:
        print("最新データが古いため、市場が閉まっている可能性があります。通知しません")
        save_state(state)
        return

    hi = max(float(c["high"]) for c in candles)
    lo = min(float(c["low"]) for c in candles)
    width = hi - lo
    print(f"直近{WINDOW_MIN}分: 高値 {hi:.3f} / 安値 {lo:.3f} / 値幅 {width:.2f}円")

    if width >= THRESHOLD_YEN and now - state["last_notified"] >= COOLDOWN_MIN * 60:
        start = float(candles[-1]["open"])
        direction = "円安方向" if rate > start else "円高方向"
        send_line(
            f"ドル円が急変動です({direction})\n"
            f"現在: {rate:.3f}円\n"
            f"直近{WINDOW_MIN}分の値幅: {width:.2f}円"
        )
        state["last_notified"] = now
        print("LINEに急変動の通知を送信しました")
    else:
        print("急変動の通知条件には達していません")

    save_state(state)


if __name__ == "__main__":
    main()
