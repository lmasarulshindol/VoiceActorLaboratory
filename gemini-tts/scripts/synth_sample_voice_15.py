"""藤優真サンプル15本を Eleven v4 で MP3 にする."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eleven_tts import ElevenV4Client  # noqa: E402

OUT = ROOT / "output" / "sample-voice-15_2026-10-06"

# 日本語男性（labels.language == ja）。kiyo は初回生成済み。
VOICES: dict[str, str] = {
    "kiyo": "KdlbMHGeafEyWqPCWkW0",  # ミドル〜ロー、落ち着いた語り
    "hiro": "E6Kc2m06tkvciUiqnUhB",  # 知的で抑制した若め
    "ryo": "pUgmTF2V1ptIKsYb6qON",  # やや低めの紳士
    "nayuta": "ZcX76PwFSkrkyI78RBTK",  # ダークなアニメヒーロー
    "sawaro": "EbuvaInXUGWtpYRUnKLQ",  # 声優寄りの安定した芝居
    "akira": "DOL4zlUH4vnnX1hByxsw",  # カリスマ・歯切れ
}

# id, filename, stability, tagged text
LINES: list[tuple[str, str, float, str]] = [
    (
        "c1",
        "01_キャラ_盤上の黒幕.mp3",
        0.42,
        "[calm][quietly][smug] ……ああ、やはり来たか。座るといい。君がここに辿り着くまでの道筋は、三通りしか用意していなかった。どれを選んでも、結末は同じだ。……怒らないでくれ。責めているわけじゃない。むしろ感心しているんだよ。最後まで、自分の意思で歩いてきたと信じられる。その素直さが、私には何より使いやすかった。",
    ),
    (
        "c2",
        "02_キャラ_沈黙の組織ボス.mp3",
        0.5,
        "[cold][low][firm] 顔を上げろ。……俺は怒鳴らない。怒鳴るのは、まだ相手に期待している人間だけだ。お前が消した荷の数、売った相手の名前、全部ここにある。言い訳は要らない。俺が聞きたいのは一つだけだ。……誰に、頼まれた。答えなくてもいい。その代わり、明日の朝日を見る人間が、一人減るだけだ。",
    ),
    (
        "c3",
        "03_キャラ_夜更けの兄貴分.mp3",
        0.38,
        "[warm][gentle][soft] おう、まだ起きてたのか。……座れよ、ほら、温かいの淹れてきた。今日のこと、気にしてるんだろ。顔に全部書いてある。いいか、失敗したってことは、ちゃんと挑んだってことだ。逃げたやつは、失敗すらできないんだからな。……ほら、冷めるぞ。飲んだら寝ろ。明日、また一緒にやり直そう。",
    ),
    (
        "c4",
        "04_キャラ_逃がさない美形.mp3",
        0.32,
        "[whispers][teasing][intimate] どうして目を逸らすの。……ほら、こっち。逃げても無駄だよ、後ろは壁だから。さっき、他の男に笑ってたよね。別に責めてない。ただ、少し気に入らなかっただけ。……ねえ、耳まで赤い。そういう顔、俺以外に見せたら駄目だよ。わかった？　……いい子だ。じゃあ、ご褒美をあげようか。",
    ),
    (
        "c5",
        "05_キャラ_最後の剣士.mp3",
        0.4,
        "[solemn][restrained] 下がっていろ。……ここから先は、俺一人で十分だ。十年前、守れなかった。剣を握る手が震えて、ただ見ていることしかできなかった。だから決めたんだ。二度と、誰も失わないと。……聞こえるか、亡霊ども。俺はもう逃げない。この命ごと、[shouting]斬り捨ててやる！　来い……！",
    ),
    (
        "n1",
        "06_ナレ_五十二年目の鉋.mp3",
        0.62,
        "[calm][documentary] 午前四時。まだ誰もいない工房に、男は灯りをともす。職人歴、五十二年。削った木の数は、本人にも分からない。……『同じ木は、ひとつもないんです』。そう言って、彼は鉋を引いた。薄い木屑が、朝の光に透ける。完璧を求めてきたのではない。ただ、昨日の自分を、少しだけ越えたかった。",
    ),
    (
        "n2",
        "07_ナレ_届かない問い.mp3",
        0.6,
        "[calm][thoughtful] 夜空に輝く星の光。その多くは、何万年も前に放たれたものだ。私たちが見ているのは、今の星ではない。遠い過去の姿である。……一九七七年に旅立った探査機は、今も太陽系の外を進み続けている。誰もいない暗闇の中で、地球の声を抱えたまま。人類が宇宙へ投げかけた問い。その答えは、まだ届いていない。",
    ),
    (
        "n3",
        "08_ナレ_刻む価値のある時間.mp3",
        0.65,
        "[calm][premium] 時間は、誰にでも平等に流れる。けれど、その刻み方は、人の数だけある。……一秒を、二百の部品が支える。職人の手で、ひとつずつ。急ぐ必要はない。本当に大切なものは、いつも静かに積み重なっていくから。あなたの人生を、刻む価値のある時間に。――機械式腕時計、アエテルナ。",
    ),
    (
        "n4",
        "09_ナレ_残り十二秒.mp3",
        0.45,
        "[tense][quietly] 残り、十二秒。スコアは一点差。三年間、ベンチを温め続けた男が、今、コートに立つ。……誰よりも早く来て、誰よりも遅く帰った。その姿を、仲間たちは知っている。ボールが、彼の手に渡った。迷いはない。[determined]跳べ。今日のために、すべてを積み上げてきたんだ。……ブザーが、鳴った。",
    ),
    (
        "n5",
        "10_ナレ_朝七時の食堂.mp3",
        0.35,
        "[cheerful][bright] さあ、今週やってきたのは、海沿いの小さな港町。お目当ては、朝七時にしか開かない伝説の食堂です。……[excited]ありました！　行列の先に、湯気の立つ丼。獲れたての地魚が、これでもかと乗っています。一口食べた常連さん、思わずこの笑顔。いったい、どんな味なのか。気になる続きは、このあとすぐ！",
    ),
    (
        "r1",
        "11_朗読_雨の踏切.mp3",
        0.55,
        "[soft][melancholic] 雨は、夕方から降り続いていた。駅のホームに立つと、線路の向こうで街の灯がにじんで見えた。彼女が最後に乗った電車も、確かこんな夜だった気がする。傘を差し出せば、何かが変わっただろうか。……いや、と僕は首を振る。変わらなかったのは、きっと僕のほうだ。遠くで、踏切の音が鳴り始めた。",
    ),
    (
        "r2",
        "12_朗読_二階の空き部屋.mp3",
        0.48,
        "[whispers][uneasy] その旅館の二階には、使われていない部屋がひとつある。仲居は、決してその前を通らない。……夜中の二時。廊下の奥から、畳を擦るような音がした。すり、すり、と。音は、私の部屋の前で止まった。襖の隙間から、白い指が一本、ゆっくりと差し込まれる。そして、聞こえたのだ。……『ここ、あいてますか』と。",
    ),
    (
        "r3",
        "13_朗読_星をかぞえるくま.mp3",
        0.4,
        "[warm][gentle][storytelling] むかし、森のはずれに、ひとりぼっちの年老いたくまが住んでいました。くまは毎晩、空を見上げて、星の数をかぞえるのが好きでした。ある冬の夜、小さなこぎつねが、ふるえながら戸をたたきました。『星が、ひとつも見えないの』。くまは、にっこり笑って言いました。『それなら、いっしょに朝まで待とう』。",
    ),
    (
        "r4",
        "14_朗読_ネオンが消えた夜.mp3",
        0.52,
        "[dry][low][noir] 依頼人は、嘘をつくとき必ず左手で煙草を探す女だった。その夜も、彼女は空のポケットを三度探った。『夫を探してほしいの』。俺は答えずに、グラスの氷を鳴らした。探す必要はない。男がどこにいるかなら、もう知っている。……問題は、誰が彼をそこへ沈めたかだ。窓の外で、ネオンが一つ消えた。",
    ),
    (
        "r5",
        "15_朗読_拝啓頑固な友へ.mp3",
        0.4,
        "[soft][wistful] 拝啓。この手紙を君が読むころ、僕はもう、そちらにはいないだろう。思えば、喧嘩ばかりの二十年だった。君の頑固さに、何度呆れたか分からない。……でもな、あの日、雨の中を走って迎えに来てくれたこと。一度も、礼を言えなかった。[emotional]ありがとう。本当に、ありがとう。どうか、君は、君らしく生きてくれ。敬具。",
    ),
]


def remaining_chars(api_key: str) -> int:
    req = Request(
        "https://api.elevenlabs.io/v1/user/subscription",
        headers={"xi-api-key": api_key},
    )
    with urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode())
    return int(data.get("character_limit") or 0) - int(data.get("character_count") or 0)


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        print("ELEVENLABS_API_KEY が未設定です。gemini-tts/.env に記入してください。")
        return 2
    wanted = [name for name in sys.argv[1:] if name in VOICES] or [
        name for name in VOICES if name != "kiyo"
    ]
    need = sum(len(text) for _, _, _, text in LINES) * len(wanted)
    left = remaining_chars(key)
    print(f"remaining={left} need~={need} voices={','.join(wanted)} model=eleven_v4")
    if left < need + 200:
        print("文字数枠が足りません")
        return 2
    client = ElevenV4Client(key)
    OUT.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for voice_name in wanted:
        voice_id = VOICES[voice_name]
        dest_dir = OUT / voice_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        for line_id, filename, stability, text in LINES:
            dest = dest_dir / filename
            if dest.is_file() and dest.stat().st_size > 1000:
                print(f"skip: {voice_name}/{filename}")
                continue
            try:
                audio = client.synthesize(text, voice_id, stability=stability, seed=7)
                dest.write_bytes(audio)
                print(f"saved: {voice_name}/{filename} bytes={dest.stat().st_size}")
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{voice_name}/{line_id}: {exc}")
                print(f"fail: {voice_name}/{line_id}: {exc}")
                if "invalid_api_key" in str(exc) or "authentication_error" in str(exc):
                    print("FAILED")
                    for item in failed:
                        print(item)
                    return 1
            time.sleep(0.4)
    if failed:
        print("FAILED")
        for item in failed:
            print(item)
        return 1
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
