"""横印刷・縦書き台本PDFを生成する（キャスト案なし）。"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT = SCRIPT_DIR / "異常な日常の物語 最適化された男_3訂.pdf"
# 横長1ページに横並びできる目安（mm）= A4 landscape 297mm - 左右余白14mm*2 - 余裕
PAGE_PRINTABLE_WIDTH_MM = 269
PAGE_USABLE_MM = 265
COL_MM = 5.2
BLOCK_GAP_MM = 2.5
# 列幅見積もりは実際の CSS 折り返しよりやや大きめ。孤立ページの吸収判定だけ緩める。
RELAXED_WIDTH_SCALE = 0.875
ORPHAN_PAGE_MAX_MM = 90.0
CHARS_PER_COL_EST = 18
EDGE_CANDIDATES = [
    Path(r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path(r"C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
]

VERTICAL_CSS = """
@page {
    size: A4 landscape;
    margin: 16mm 14mm;
}
html, body {
    font-family: "Yu Mincho", "Yu Mincho Light", "ヒラギノ明朝 Pro", "MS PMincho", serif;
    font-size: 10.5pt;
    line-height: 1.85;
    color: #111;
    background: #fff;
    writing-mode: horizontal-tb;
}
body {
    margin: 0;
    padding: 0;
}
.title {
    font-size: 18pt;
    letter-spacing: 0.15em;
    margin: 0 0 1.2em;
    border-right: 1px solid #666;
    padding-right: 0.35em;
}
.subtitle {
    font-size: 11pt;
    color: #333;
    margin: 0 0 1.6em;
}
h2 {
    font-size: 13pt;
    margin: 1.4em 0 0.7em;
    padding-right: 0.35em;
    border-right: 3px solid #444;
}
.cast-list {
    margin: 0.5em 0 1.2em;
    font-size: 9.5pt;
}
.cast-entry {
    margin: 0 0 1em;
    padding-right: 0.35em;
    border-right: 1px solid #bbb;
}
.cast-name {
    font-weight: 700;
    font-size: 10.5pt;
    margin-bottom: 0.3em;
}
.cast-desc {
    margin-bottom: 0.25em;
}
.cast-scenes {
    color: #444;
    font-size: 9.5pt;
}
.cast-label {
    font-weight: 700;
    font-size: 9pt;
    color: #555;
    margin-right: 0.2em;
}
.scene {
    font-size: 12pt;
    font-weight: 700;
    margin: 1.2em 0 0.6em;
    padding-right: 0.3em;
    border-right: 2px solid #555;
    page-break-inside: avoid;
    break-inside: avoid;
}
.front-matter,
.cover-page {
    box-sizing: border-box;
    width: 269mm;
    height: 170mm;
    overflow: hidden;
}
.cover-flow {
    writing-mode: vertical-rl;
    -webkit-writing-mode: vertical-rl;
    text-orientation: mixed;
    height: 170mm;
    overflow: hidden;
}
.script-body {
    margin-top: 0;
}
.script-page {
    display: flex;
    flex-direction: row-reverse;
    flex-wrap: nowrap;
    align-items: flex-start;
    width: 269mm;
    height: 170mm;
    overflow: hidden;
    box-sizing: border-box;
    position: relative;
}
.script-page::before {
    content: "";
    position: absolute;
    top: 51mm;
    left: 0;
    right: 0;
    border-top: 1px solid #bbb;
    pointer-events: none;
    z-index: 2;
}
.script-body .script-page + .script-page {
    page-break-before: always;
    break-before: page;
}
.scene-block,
.script-block {
    flex: 0 0 auto;
    position: relative;
    z-index: 1;
}
.scene-block {
    background: #fff;
    display: inline-block;
    height: 170mm;
    width: max-content;
    vertical-align: top;
    margin-inline: 0.45em;
}
.scene-block .scene {
    margin: 0;
    height: 100%;
    writing-mode: vertical-rl;
    -webkit-writing-mode: vertical-rl;
}
.script-flow {
    margin-top: 0;
}
.script-block {
    display: inline-block;
    height: 170mm;
    width: max-content;
    vertical-align: top;
    margin-inline: 0.45em;
    position: relative;
}
.script-block.has-stage::before {
    content: "";
    position: absolute;
    inset-inline-end: -0.35em;
    top: 0;
    bottom: 0;
    border-inline-end: 1px solid #bbb;
}
.block-inner {
    display: flex;
    flex-direction: column;
    height: 170mm;
    width: max-content;
    writing-mode: horizontal-tb;
}
.block-top {
    writing-mode: vertical-rl;
    -webkit-writing-mode: vertical-rl;
    text-orientation: mixed;
    color: #444;
    font-size: 10pt;
    line-height: 1.75;
    overflow: hidden;
    box-sizing: border-box;
    flex: 0 0 50mm;
    height: 50mm;
    min-height: 50mm;
    max-height: 50mm;
    width: max-content;
    padding-bottom: 1mm;
}
.block-bottom {
    writing-mode: vertical-rl;
    -webkit-writing-mode: vertical-rl;
    text-orientation: mixed;
    font-size: 10.5pt;
    line-height: 1.75;
    overflow: hidden;
    box-sizing: border-box;
    flex: 0 0 118mm;
    height: 118mm;
    max-height: 118mm;
    width: max-content;
    margin-top: 2mm;
    padding-top: 1.5mm;
}
.block-top .stage-item + .stage-item {
    margin-inline-start: 0.6em;
}
.block-bottom .dialogue + .dialogue {
    margin-inline-start: 0.8em;
}
.dialogue .speaker {
    font-weight: 700;
}
.dialogue .line {
    margin-inline-start: 0.15em;
}
.dialogue .cont-label {
    font-weight: 400;
    font-size: 9pt;
    color: #666;
}
hr {
    border: none;
    border-right: 1px dashed #aaa;
    margin: 1.2em 0;
}
"""

HTML_HEAD = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>異常な日常の物語 最適化された男</title>
<style>
{css}
</style>
</head>
<body>
"""

HTML_TAIL = """
</body>
</html>
"""

CAST_ROWS = [
    ("語り手", "ナレーター。本編には介入しない", "プロローグ・エピローグ"),
    ("佐藤", "主人公。アプリ「Life Player」で現実を早送りし続ける会社員", "全シーン"),
    ("田中", "佐藤の同僚（後輩）", "S1・S2"),
    ("恵美", "佐藤の恋人→妻。病室時点では故人", "S3・S4・S6"),
    ("部長", "佐藤の上司", "S2（会議）・S5（叱責）"),
    ("看護師", "病室で家族を呼ぶ声のみ", "S7（1行）"),
    ("サキ", "佐藤と恵美の娘", "S6（幼少〜少女の声）・S7（成人）"),
    ("車内アナウンス", "満員電車の案内放送", "S2（1行）"),
    ("同僚たち", "飲み会のガヤ", "S2（1行）"),
]

SCRIPT_BLOCKS: list[tuple[str, str]] = [
    ("scene", "プロローグ"),
    (
        "dialogue",
        "語り手",
        "「効率、タイパ、時短……。現代人はとにかく『無駄』を嫌います。無駄な時間を削り、最短距離で幸せを掴もうとする。しかし、もしその『無駄』の中にこそ、人間が人間であるための重要な何かが隠されていたとしたら……？今夜お見せするのは、そんな効率を追い求めすぎた男の、少しばかり異常な日常の物語です」",
    ),
    ("scene", "シーン１：深夜のオフィス"),
    ("dialogue", "田中（後輩）", "「お疲れ様です、佐藤さん。まだ残るんですか？」"),
    (
        "dialogue",
        "佐藤",
        "「あぁ。明日の朝イチまでにこの企画書上げなきゃいけなくて。……ったく、部長のあの長い説教さえなけりゃ、とっくに終わってたんだけどな」",
    ),
    ("dialogue", "田中", "「（苦笑）今日も40分超えてましたもんね」"),
    (
        "dialogue",
        "佐藤",
        "「ほんと時間の無駄。あーあ、現実も動画みたいに倍速再生できりゃいいのにな。……ん？なんだこれ」",
    ),
    ("dialogue", "田中", "「どうしました？」"),
    (
        "dialogue",
        "佐藤",
        "「いや、スマホに変なアプリが入ってる。『Life Player』……？入れた覚えなんてないんだけど……うわ、なんだこれ。勝手に画面が……」",
    ),
    (
        "dialogue",
        "田中",
        "「どれですか？……あ、ホントだ。再生ボタンとか倍速の設定画面みたいですね。誰かが作ったジョークアプリじゃないですか？」",
    ),
    ("dialogue", "佐藤", "「……試しにこの『1.5倍速』、押してみるか。（画面をタップする）」"),
    ("stage", "（カチッ、という電子音）"),
    ("dialogue", "佐藤", "「……え？田中、お前、動き早くないか？喋り方も……」"),
    (
        "dialogue",
        "田中（1.5倍速）",
        "「エ？ナニ言ッテルンデスカ佐藤サン。ボクハ普通デスヨ。ソレヨリ早ク仕事片付ケマショウ！」",
    ),
    (
        "dialogue",
        "佐藤",
        "「（驚愕）嘘だろ……。全部速い……周りの動きが全部……！待て待て待て！（慌ててスマホの画面をタップする）えっと、『等倍』……！」",
    ),
    ("stage", "（ピピッ、という電子音）"),
    (
        "dialogue",
        "田中（等倍）",
        "「――仕事片付けましょう！……って、どうしたんですか急に？画面なんか睨みつけて」",
    ),
    (
        "dialogue",
        "佐藤",
        "「（息を呑んで）……戻った。おい田中、お前、今なんか変じゃなかったか？動きとか、喋りとか……」",
    ),
    (
        "dialogue",
        "田中",
        "「変？何寝ぼけたこと言ってるんですか。さては相当疲れてますね？早く終わらせて帰りましょうよ。（自分のデスクに戻っていく）」",
    ),
    (
        "dialogue",
        "佐藤",
        "「（田中の背中を見つめながら、手元のスマホに視線を落とす）……気のせいじゃない。このアプリ、マジで周りの時間を早送りしやがった……」",
    ),
    (
        "dialogue",
        "佐藤",
        "「（画面をスクロールしながら、徐々に口角が上がっていく）……ってことは、これさえ使えば、あのクソ長い会議も、満員電車も、飲み会も……全部一瞬で終わるのか……？」",
    ),
    ("dialogue", "佐藤", "「……ふっ、ははっ。なんだよこれ……最高じゃないか」"),
    ("scene", "シーン２：倍速生活・蜜月期"),
    ("stage", "（画面に「3日後」のテロップ。軽快なBGMが立ち上がり、テンポよく場面が切り替わっていく）"),
    ("stage", "＜朝の満員電車＞"),
    ("stage", "（ぎゅうぎゅう詰めの車内音、ドアが閉まる音）"),
    ("dialogue", "佐藤", "「（スマホをタップする）3.0倍速」"),
    ("stage", "（ピピッ）"),
    ("stage", "（車内アナウンスが甲高い早回しになり、駅名が矢継ぎ早に流れていく）"),
    ("dialogue", "車内アナウンス（3.0倍速）", "「ツギハ～新宿～新宿～オ出口ハ……」"),
    ("dialogue", "佐藤", "「（涼しい顔で）……もう着いた。マジで一瞬だな」"),
    ("stage", "＜午後の会議室＞"),
    (
        "dialogue",
        "部長（2.0倍速）",
        "「エー、ソレデハ次ノ議題デスガ……コノ件ニツイテハ前回モ申シ上ゲタ通リ……（延々と続く）」",
    ),
    ("dialogue", "佐藤", "「（ノートに要点だけメモしながら、余裕の表情）結論だけ拾えば十分だな」"),
    ("dialogue", "田中（2.0倍速・隣の席から小声で）", "「佐藤サン、今日ヤケニ落チ着イテマスネ」"),
    ("dialogue", "佐藤", "「（小声で）ん？まあな。最近、会議が苦じゃなくなってさ」"),
    ("stage", "＜夕方の飲み会＞"),
    ("stage", "（居酒屋の喧騒。ジョッキがぶつかる音）"),
    (
        "dialogue",
        "同僚たち（3.0倍速）",
        "「カンパーイ！イヤー今日モ疲レタナー！ソウイエバ聞イタ？営業二課ノ鈴木サンガサー！（笑い声が甲高く響く）」",
    ),
    (
        "dialogue",
        "佐藤",
        "「（ビールをちびちび飲みながら、穏やかに微笑んでいる）笑うとこで笑って、頷くとこで頷く。ただそれだけ。……あれ、もうお開き？悪くないな」",
    ),
    ("stage", "＜翌朝のオフィス＞"),
    ("stage", "（佐藤がデスクでコーヒーを飲んでいる。田中が駆け寄ってくる）"),
    (
        "dialogue",
        "田中",
        "「佐藤さん！部長がめちゃくちゃ褒めてましたよ！『最近の佐藤は会議で一切グチを言わなくなったし、嫌な顔ひとつしない。ストレス耐性がついたな、見直した』って！」",
    ),
    ("dialogue", "佐藤", "「（満足げに笑う）そうか。まあ、ちょっとコツを掴んだだけだよ」"),
    (
        "dialogue",
        "田中",
        "「コツって何ですか？俺にも教えてくださいよ！……あ、それと。昨日の飲み会で俺が相談した件、考えてくれました？」",
    ),
    ("dialogue", "佐藤", "「（一瞬固まる）……ああ、うん。もちろん。あれな。……もうちょっと待ってくれ」"),
    ("dialogue", "田中", "「（少し寂しそうに）……そうっすか。じゃあ、また今度」"),
    (
        "dialogue",
        "佐藤",
        "「（田中の背中を見送りながら、スマホをポケットの中でそっと撫でる）……企業秘密、かな」",
    ),
    ("stage", "（佐藤が一人になったオフィスで、窓の外を見ながら独り言。BGMがフェードアウトしていく）"),
    (
        "dialogue",
        "佐藤",
        "「（モノローグ）通勤、会議、飲み会……。全部、もう苦じゃない。評価も上がった。……いや正確には、苦痛を感じなくなっただけか。まぁ同じことだろ。……もう無駄な時間なんて、ひとつも残ってない」",
    ),
    (
        "stage",
        "（佐藤がスマホの画面を見つめる。画面にはLife Playerの倍速設定バーが表示されている。佐藤の指が、無意識に速度を少し上げる。カメラが佐藤の目をクローズアップ――その瞳に、画面の光が冷たく反射している）",
    ),
    ("scene", "シーン３：三週間後のカフェ（転落の始まり）"),
    ("dialogue", "恵美", "「ねえ、聞いてる？だから、今の部署のままだと先が見えないっていうか……」"),
    ("dialogue", "佐藤", "「（スマホを操作しながら）うん、そうだね。大変だよな」"),
    ("dialogue", "恵美", "「ちょっと、聞いてないでしょ。スマホ置いてよ」"),
    ("dialogue", "佐藤", "「聞いてるって。……（画面をタップする）」"),
    ("dialogue", "佐藤", "「（モノローグ）恵美の愚痴はいつも長い。結論だけ拾えば問題ない。……今までもそうしてきた」"),
    ("stage", "（ピピッ）"),
    (
        "dialogue",
        "恵美（4.0倍速）",
        "「ダッテサァ！アノ課長ゼッタイ私ノコト評価シテナイシ！コノママトシトッテモ……（凄まじい早口で捲し立てる）」",
    ),
    ("dialogue", "佐藤", "「（涼しい顔でコーヒーを一口飲む）はいはい」"),
    (
        "dialogue",
        "恵美（4.0倍速）",
        "「ソレニネ！コノマエモ先輩ガサァ！私ノ企画書勝手ニ名前変エテ出シタノヨ！？シンジラレナイ！」",
    ),
    ("dialogue", "佐藤", "「（窓の外の景色を眺めながら、適当に頷く）うん、わかるよ」"),
    (
        "dialogue",
        "恵美（4.0倍速）",
        "「アァモウ思イ出シタダケデ腹タツ！ソウイエバコノ前ノ旅行ノ時モサァ……！（身振りを交えて怒濤の愚痴が止まらない）」",
    ),
    ("dialogue", "佐藤", "「（手元のスマホでニュース記事をスクロールしながら）へえ、そうなんだ」"),
    (
        "dialogue",
        "恵美（4.0倍速）",
        "「ダカラ私モウ限界デ……（急に涙ぐみ、ハンカチで目元を拭う）……ソレニネ、最近チョット体調モ悪クテ……病院行ッタラ精密検査シタ方ガイイッテ……デモ、健太郎ガソウ言ッテクレルナラ……（照れたようにモジモジし始める）」",
    ),
    ("dialogue", "佐藤", "「お、そろそろ結論だな。（画面をタップする）」"),
    ("stage", "（ピピッ）"),
    ("dialogue", "恵美（等倍）", "「――っていうわけなの。ね、私の気持ち、わかってくれた？」"),
    (
        "dialogue",
        "佐藤",
        "「（スマホをポケットにしまい、真剣な表情を作って）ほんとだよな。恵美の言う通りだよ」",
    ),
    ("dialogue", "恵美", "「（パッと表情を明るくして）本当！？じゃあ、来月の連休、うちの両親に挨拶行ってくれるんだね！」"),
    ("dialogue", "佐藤", "「（コーヒーのカップを持ったままフリーズする）……は？」"),
    (
        "dialogue",
        "恵美",
        "「だから、『今の仕事辞めて家庭に入りたいから、そろそろちゃんと話したい』ってさっき言ったじゃない。ね？」",
    ),
    ("dialogue", "佐藤", "「（顔が引きつる）あ、いや……それは……もちろん。前向きに……調整するよ」"),
    ("scene", "シーン４：ある日の自宅・洗面所"),
    ("stage", "（水道の蛇口をひねる音。佐藤が鏡の前で顔を洗っている）"),
    (
        "dialogue",
        "佐藤",
        "「（鏡に映る自分の顔を見つめる）……なんだ、このクマ。最近ちゃんと寝てるはずなのに……いや、寝てたのか？寝た記憶が……ない」",
    ),
    ("stage", "（リビングから恵美の声が聞こえてくる）"),
    (
        "dialogue",
        "恵美（等倍・少し離れた場所から）",
        "「ねえ、健太郎。今日は日曜でしょ？サキと一緒に公園行かない？最近あの子、パパと全然遊べてないって寂しがって……」",
    ),
    ("dialogue", "佐藤", "「（反射的にスマホに手を伸ばしかけて、止まる）…………」"),
    (
        "dialogue",
        "佐藤",
        "「（独白、低い声で）……最近、恵美やサキと一緒にいるときも、気づくと倍速にしてる。飯も風呂も、通勤も、寝る前のサキの絵本も……。全部、早く終わらせたくなる」",
    ),
    ("dialogue", "佐藤", "「（スマホの画面を見つめる）……等倍に戻せばいい。それだけのことだ。……戻せば……」"),
    ("stage", "（長い沈黙）"),
    ("dialogue", "佐藤", "「（画面をタップする）……2.0倍速」"),
    ("stage", "（ピピッ）"),
    (
        "dialogue",
        "恵美（2.0倍速）",
        "「モウ！聞イテルノ？サキガ待ッテルンダケド……アト、来週ノ検査結果聞キニ行クカラ、火曜日ハ早ク帰ッテキテネ」",
    ),
    ("dialogue", "佐藤", "「（気まずそうに目を逸らしながら）……わかった。ああ、わかったよ」"),
    ("scene", "シーン５：部長室"),
    ("dialogue", "佐藤（ひどくやつれ、白髪が目立っている）", "「部長、失礼します。例のプロジェクトの件ですが……」"),
    (
        "dialogue",
        "部長（等倍）",
        "「佐藤くん。座りなさい。……最近、会議中に上の空なことが多いと報告を受けている。先週の企画会議でクライアントの名前を間違えたのも君だな？」",
    ),
    ("dialogue", "佐藤", "「それは……申し訳ありません」"),
    (
        "dialogue",
        "部長（等倍）",
        "「それだけじゃない。今朝の報告書、データが先月のものと丸ごと同じだった。確認すらしていないだろう」",
    ),
    ("dialogue", "佐藤", "「（言葉に詰まる）……いえ、確認は……」"),
    (
        "dialogue",
        "部長（等倍）",
        "「言い訳はいい。正直に言ってくれ。何か問題を抱えているのか？ここ半年ほど、君はまるで――」",
    ),
    (
        "dialogue",
        "佐藤",
        "「（焦り始め、ポケットのスマホに手を伸ばす）（小声で）……きつい。長くなりそうだ、この説教。早く……終わってくれ……」",
    ),
    ("stage", "（ピピッ）"),
    (
        "dialogue",
        "部長（8.0倍速）",
        "「――会社ニハ来テイルノニドコカ上ノ空ダトイウカ！ソレデハ部下モツイテコナイゾ！（甲高い声でまくし立てる）」",
    ),
    ("dialogue", "佐藤", "「（少しだけ安堵した表情で、やり過ごそうとする）……結論だけ拾えばいい。いつも通り――」"),
    (
        "dialogue",
        "部長（8.0倍速）",
        "「コノママダト君ノ評価ニモ関ワルゾ！責任取レルノカ！？（机の書類を高速でバンバン叩く）」",
    ),
    (
        "dialogue",
        "佐藤",
        "「（異変に気づく）……ん？待てよ。なんか……速すぎないか……？おい、等倍に……（画面をタップする）……戻らない？」",
    ),
    ("stage", "（スマホから『ピロリン』と無機質な通知音が鳴る）"),
    ("dialogue", "佐藤", "「……なんだよ、今頃」"),
    ("stage", "（画面に【最適化を実行中：強制的に16.0倍速へ移行します】のポップアップ表示）"),
    ("dialogue", "佐藤", "「は……？冗談だろ、おい、キャンセル……キャンセルどこだ！」"),
    ("stage", "（ピピッ）"),
    (
        "dialogue",
        "部長（16.0倍速）",
        "「（もはや虫の羽音のような『ジーーーッ』というノイズしか聞こえず、残像が見えるほどの速度で口をパクパクさせている）」",
    ),
    ("dialogue", "佐藤", "「部長！待って……待ってください！俺の話も……っ！」"),
    (
        "stage",
        "（周囲の社員たちが残像のように動き回り、オフィスの時計の針が扇風機のように猛スピードで回転し始める）",
    ),
    ("dialogue", "佐藤", "「やめろ……！止まれ！！誰か……！！」"),
    ("stage", "（周囲の景色が嵐のように乱れ、佐藤の悲鳴がノイズに飲み込まれる）"),
    ("scene", "シーン６：人生ダイジェスト"),
    (
        "stage",
        "（全ての音が一瞬止まる。静寂。そして、微かな電子音とともに、断片的な音声が矢継ぎ早に重なり始める）",
    ),
    ("dialogue", "恵美（断片的、エコーがかかっている）", "「……検査の結果が出たの。……健太郎、聞いて……」"),
    ("stage", "（ピピッ）"),
    ("dialogue", "サキ（幼い声、遠い残響）", "「パパ、見て！お絵描きしたの！パパ……パパ？」"),
    ("stage", "（ピピッ）"),
    ("dialogue", "恵美（断片的、震える声）", "「……お願い、こっち見て。スマホじゃなくて、私を……」"),
    ("stage", "（ピピッ）"),
    ("dialogue", "サキ（少し成長した声）", "「ママ、パパは来ないの？運動会……」"),
    ("stage", "（ピピッ）"),
    ("dialogue", "恵美（断片的、弱々しく）", "「……もう、いいよ。……ありがとう。幸せだったよ……」"),
    ("stage", "（ピピッ）"),
    (
        "stage",
        "（全ての声が重なり、ノイズに変わり、やがて一本の長い心電図のアラーム音──ピーーーーー──に収束していく。それは恵美の最期を示す音。しかし佐藤の耳には、16倍速のノイズとして一瞬で通過する）",
    ),
    ("dialogue", "佐藤", "「……え？今……誰かが、呼んで……」"),
    ("stage", "（沈黙。佐藤の荒い呼吸だけが残る）"),
    ("scene", "シーン７：真っ白な病室"),
    (
        "stage",
        "（機械的なバイタル音が、非常に速いテンポで鳴り響いている。ピー、ピー、ピー、という音が次第にゆっくりになり、等倍の速度に落ち着く）",
    ),
    ("dialogue", "看護師（等倍）", "「ご家族の方、今のうちにお声がけを……。（足早に立ち去る）」"),
    ("dialogue", "謎の女性（30代ほどの落ち着いた声）", "「……お父さん。わかる？」"),
    ("dialogue", "佐藤（ひどく掠れた声、顔には酸素マスク）", "「……恵美、か……？お前、ずいぶん……」"),
    ("dialogue", "女性", "「……何言ってるの。サキよ」"),
    ("dialogue", "佐藤", "「……サキ……？」"),
    (
        "dialogue",
        "女性",
        "「お母さんは……5年前に亡くなったでしょ。お父さん、お葬式の日も……ずっとスマホの画面を見てた」",
    ),
    ("dialogue", "佐藤", "「（力なく目を見開く）……は……？なくなっ……？恵美が……？」"),
    (
        "dialogue",
        "女性",
        "「お母さん、ずっと言ってたよ。検査の結果のこと、ちゃんと聞いてほしいって。……でも、お父さんには届かなかった」",
    ),
    ("dialogue", "佐藤", "「（声が震える）検査……？あの時の、検査って……」"),
    (
        "dialogue",
        "女性",
        "「お母さんだけじゃない。私の卒業式も、成人式も、結婚式も……。お父さんはいつもそこにいたのに、どこにもいなかった」",
    ),
    ("dialogue", "佐藤", "「（絶句する）…………」"),
    (
        "dialogue",
        "女性",
        "「……もういいの。最後にお父さんの目が、ちゃんとこっちを見てる。それだけで十分。……お疲れ様」",
    ),
    ("dialogue", "佐藤", "「待て……サキ……？お前、いつの間にそんな大人に……！恵美は、どこだ……！」"),
    ("stage", "（佐藤の震える手が、シーツの上にあった古いスマホに触れる。画面が鈍く光る）"),
    ("stage", "【全編再生終了】"),
    ("dialogue", "佐藤", "「（荒い息を吐きながら）……嘘だろ……。俺の……時間……」"),
    ("stage", "（画面が切り替わり、ポップアップが表示される）"),
    (
        "stage",
        "【プレミアム会員に登録して、人生をリプレイしますか？】※無料プランの場合、30秒の動画広告の視聴が必要です。【▶広告を見る】",
    ),
    ("dialogue", "佐藤", "「（必死に手を伸ばす。指先が震え、うまく動かない）……あ……押せ……押してくれ……！」"),
    ("stage", "（サキは悲しげに目を伏せ、そのまま病室を出ていく）"),
    ("dialogue", "佐藤", "「サキ……！頼む……！その、ボタンを……！」"),
    ("stage", "（指が画面に触れる直前、心電図の長く平坦なアラーム音が響き渡る。ピーーーーーッ）"),
    ("stage", "（スマホの画面が、プツンと暗転する）"),
    ("scene", "エピローグ"),
    (
        "dialogue",
        "語り手",
        "「プレミアム会員への登録……彼は無事に済ませることができたのでしょうか。まあ、仮に間に合ったとしても、あの忌々しい30秒の広告を、彼が大人しく等倍で待てたとは思えませんがね」",
    ),
    (
        "dialogue",
        "語り手",
        "「おや、いけません。現代を生きるお忙しい皆様から、これ以上時間を奪うのは無粋というものでしょう。私もそろそろ失礼します」",
    ),
    ("dialogue", "語り手", "「……ところで。皆様は今、この物語を『等倍』でご覧になっていましたか？」"),
    (
        "dialogue",
        "語り手",
        "「お気をつけください。あなたのその指先が、あなたの人生そのものを早送りしてしまわないとも、限りませんから。それでは……また。」",
    ),
]


# ---------------------------------------------------------------------------
# ト書き / セリフ内() 分類ルール
# ---------------------------------------------------------------------------
# 【ト書き（上段）】
#   - SE・効果音・環境音・BGM・沈黙
#   - 場所・時間・場面転換（＜＞）、画面演出（テロップ/UI/ポップアップ/【】）
#   - 話者以外の動き、背景・カメラ・集合描写
#   - 話者の道具操作・移動・視線移動（タップ、戻る、見送る、スクロール等）
#   - セリフ末尾の非発話描写（笑い声が響く、足早に立ち去る、口をパクパク等）
#   - 話者名の外見・身体状態（ひどくやつれ…）は上段へ
#
# 【セリフ内 ()】
#   - 感情・表情・声質の演技指示（苦笑、驚愕、小声で、等）
#   - モノローグ/独白の読み方指定
#   - セリフと同時の短い心理・表情（息を呑んで、一瞬固まる等）
#
# 【話者名に残す】
#   - 倍速/等倍、声のタイプ（幼い声、断片的、エコー等）、役柄（後輩）
# ---------------------------------------------------------------------------

PAREN_RE = re.compile(r"（([^）]+)）")
SPEAKER_SUFFIX_RE = re.compile(r"^(.+?)（(.+?)）$")
SPEAKER_KEEP_SUFFIX = re.compile(
    r"(倍速|等倍|後輩|幼い声|成長した声|断片的|エコー|残響|離れた|掠れた声|酸素マスク|落ち着いた声|震える声|弱々しく)"
)

DELIVERY_PATTERNS = [
    r"苦笑",
    r"驚愕",
    r"小声",
    r"モノローグ",
    r"独白",
    r"低い声",
    r"固ま",
    r"満足",
    r"寂し",
    r"気まず",
    r"焦り",
    r"安堵",
    r"異変",
    r"絶句",
    r"息を呑",
    r"涼しい顔",
    r"余裕",
    r"真剣",
    r"引きつ",
    r"フリーズ",
    r"力なく",
    r"荒い息",
    r"必死",
    r"震え",
    r"言葉に詰",
    r"パッと表情",
    r"表情を明るく",
    r"反射的",
    r"甲高い声で",
    r"やり過ごそ",
    r"コーヒーのカップを持ったまま",
]

STAGE_PATTERNS = [
    r"タップ",
    r"画面",
    r"スマホ",
    r"デスク",
    r"戻っ",
    r"撫で",
    r"スクロール",
    r"見つめ",
    r"眺め",
    r"伸ば",
    r"触れ",
    r"立ち去",
    r"出ていく",
    r"伏せ",
    r"ノート",
    r"蛇口",
    r"鏡",
    r"シーツ",
    r"ポケット",
    r"カメラ",
    r"テロップ",
    r"BGM",
    r"ポップアップ",
    r"見送",
    r"背中",
    r"ビール",
    r"ジョッキ",
    r"机",
    r"書類",
    r"時計",
    r"社員",
    r"景色",
    r"手が",
    r"指が",
    r"サキは",
    r"リビング",
    r"窓",
    r"電子音",
    r"通知音",
    r"アラーム",
    r"笑い声",
    r"口をパク",
    r"延々と続く",
    r"凄まじい早口",
    r"身振り",
    r"足早",
    r"バイタル",
    r"心電図",
    r"暗転",
    r"ノイズ",
    r"残像",
    r"回転",
    r"嵐",
    r"一人にな",
    r"駆け寄",
    r"洗っ",
    r"声が聞こえ",
    r"フェード",
    r"急に涙",
    r"ハンカチ",
    r"照れたように",
    r"慌てて",
    r"操作",
    r"記事",
    r"メモ",
    r"ぎゅうぎゅう",
    r"居酒屋",
    r"喧騒",
    r"満員",
    r"全ての音",
    r"静寂",
    r"重なり",
    r"収束",
    r"呼吸",
    r"古いスマホ",
    r"切り替わ",
    r"表示",
    r"もはや",
    r"ひどくやつれ",
    r"白髪",
    r"カチッ",
    r"ピピッ",
    r"ピロリン",
    r"ピー",
    r"コーヒーを",
    r"ニュース",
    r"病室",
    r"酸素",
    r"【",
    r"▶",
]


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def classify_parenthetical(content: str) -> str:
    """Return 'stage' or 'delivery'."""
    if _matches_any(DELIVERY_PATTERNS, content) and not _matches_any(STAGE_PATTERNS, content):
        return "delivery"
    if _matches_any(STAGE_PATTERNS, content):
        return "stage"
    if re.search(r"(を|が|に|で|へ|から).*(る|く|む|ぶ|つ|す|み|い|て|で|せ|ね|よ|わ)$", content):
        return "stage"
    return "delivery"


def split_speaker(speaker: str) -> tuple[str, list[str]]:
    m = SPEAKER_SUFFIX_RE.match(speaker)
    if not m:
        return speaker, []
    name, note = m.group(1), m.group(2)
    if SPEAKER_KEEP_SUFFIX.search(note):
        return speaker, []
    return name, [f"（{note}）"]


def extract_paren_from_dialogue(text: str) -> tuple[list[str], str]:
    stages: list[str] = []

    def replacer(match: re.Match[str]) -> str:
        content = match.group(1)
        if classify_parenthetical(content) == "stage":
            stages.append(f"（{content}）")
            return ""
        return match.group(0)

    cleaned = PAREN_RE.sub(replacer, text)
    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = re.sub(r"「」", "", cleaned)
    if cleaned in ("「」", ""):
        cleaned = ""
    elif not cleaned.startswith("「"):
        cleaned = f"「{cleaned.lstrip('「')}"
    return stages, cleaned


def normalize_script_blocks(blocks: list[tuple]) -> list[tuple]:
    """1セリフ=1ブロック単位に再構成し、()内ト書きを上段へ移す。"""
    result: list[tuple] = []
    pending_stages: list[str] = []

    for block in blocks:
        kind = block[0]
        if kind == "scene":
            pending_stages = []
            result.append(block)
            continue
        if kind == "stage":
            pending_stages.append(block[1])
            continue

        _, speaker, text = block
        speaker, speaker_stages = split_speaker(speaker)
        text_stages, clean_text = extract_paren_from_dialogue(text)
        stages = pending_stages + speaker_stages + text_stages
        pending_stages = []

        if clean_text or stages:
            result.append(("unit", stages, speaker, clean_text))

    if pending_stages:
        result.append(("unit", pending_stages, "", ""))

    return result


# 縦書き1列の文字数（vcol高さ・pt・line-height から算出）
TOP_VCOL_MM = 50.0
BOTTOM_VCOL_MM = 118.0
LINE_HEIGHT = 1.75


def _chars_per_column(height_mm: float, font_pt: float) -> int:
    char_mm = font_pt * LINE_HEIGHT * 25.4 / 72
    return max(1, int(height_mm / char_mm))


TOP_CHARS_PER_COL = _chars_per_column(TOP_VCOL_MM, 10)           # ≒8
BOTTOM_CHARS_WITH_STAGE = _chars_per_column(BOTTOM_VCOL_MM, 10.5)  # ≒18

# 1ブロックに収める列数（続き分割の目安）
MAX_COLUMNS_PER_BLOCK = 12
CHARS_PER_COLUMN = BOTTOM_CHARS_WITH_STAGE
MAX_CHARS_PER_UNIT = CHARS_PER_COLUMN * MAX_COLUMNS_PER_BLOCK


def _split_body_at_boundaries(body: str, max_len: int) -> list[str]:
    if len(body) <= max_len:
        return [body]
    chunks: list[str] = []
    rest = body
    while rest:
        if len(rest) <= max_len:
            chunks.append(rest)
            break
        cut = max_len
        for sep in ("。", "！", "？", "……", "、", " "):
            pos = rest.rfind(sep, 0, max_len + 1)
            if pos > max_len // 3:
                cut = pos + len(sep)
                break
        chunks.append(rest[:cut])
        rest = rest[cut:]
    return chunks


def split_long_units(blocks: list[tuple]) -> list[tuple]:
    """長いセリフを続きブロックに分割（2行目以降は名前省略）。"""
    result: list[tuple] = []
    for block in blocks:
        if block[0] != "unit":
            result.append(block)
            continue
        _, stages, speaker, text = block
        if not text or len(text) <= MAX_CHARS_PER_UNIT:
            result.append(block)
            continue
        body = text[1:-1] if text.startswith("「") and text.endswith("」") else text
        for i, chunk in enumerate(_split_body_at_boundaries(body, MAX_CHARS_PER_UNIT - 2)):
            chunk_text = f"「{chunk}」"
            if i == 0:
                result.append(("unit", stages, speaker, chunk_text))
            else:
                result.append(("unit", [], "", chunk_text))
    return result


def find_edge() -> Path:
    for candidate in EDGE_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Microsoft Edge (msedge.exe) が見つかりませんでした。")


def estimate_columns(text_len: int, chars_per_col: int) -> int:
    if text_len <= 0:
        return 0
    return max(1, (text_len + chars_per_col - 1) // chars_per_col)


def render_script_block(stages: list[str], dialogues: list[tuple[str, str]]) -> str:
    """dialogues: (話者, セリフ) の列。話者が空なら続き扱い。"""
    has_stage = bool(stages)
    cls = "script-block has-stage" if has_stage else "script-block"
    if dialogues and not dialogues[0][0]:
        cls += " continuation"

    parts = [f'<div class="{cls}"><div class="block-inner">']

    parts.append('<div class="block-top">')
    for stage in stages:
        parts.append(f'<span class="stage-item">{stage}</span>')
    parts.append("</div>")

    parts.append('<div class="block-bottom">')
    for speaker, text in dialogues:
        if not text:
            continue
        if speaker:
            parts.append(
                f'<div class="dialogue"><span class="speaker">{speaker}</span>'
                f'<span class="line">{text}</span></div>'
            )
        else:
            parts.append(
                f'<div class="dialogue"><span class="speaker cont-label">（続き）</span>'
                f'<span class="line">{text}</span></div>'
            )
    parts.append("</div>")

    parts.append("</div></div>")
    return "".join(parts)


def verify_text_integrity() -> list[str]:
    """生成前にセリフ欠落がないか検証。問題があればメッセージを返す。"""
    errors: list[str] = []
    html = build_html()
    plain = re.sub(r"<[^>]+>", "", html)
    units = split_long_units(normalize_script_blocks(SCRIPT_BLOCKS))

    for b in units:
        if b[0] == "unit" and b[3] and b[3] not in plain:
            errors.append(f"ユニット未出力: {b[3][:50]}")
        if b[0] == "unit" and b[2] and b[3] and b[2] not in plain:
            errors.append(f"話者名未出力: {b[2]}")

    orig_spoken: list[str] = []
    for block in SCRIPT_BLOCKS:
        if block[0] != "dialogue":
            continue
        _, _, text = block
        _, clean = extract_paren_from_dialogue(text)
        if not clean:
            continue
        body = clean[1:-1] if clean.startswith("「") and clean.endswith("」") else clean
        orig_spoken.append(body)

    norm_spoken: list[str] = []
    for b in units:
        if b[0] == "unit" and b[3]:
            body = b[3][1:-1] if b[3].startswith("「") and b[3].endswith("」") else b[3]
            norm_spoken.append(body)

    if "".join(orig_spoken) != "".join(norm_spoken):
        errors.append(
            f"セリフ本文不一致: 正規化前={len(''.join(orig_spoken))}字 "
            f"生成後={len(''.join(norm_spoken))}字"
        )

    return errors


def estimate_block_width_mm(stages: list[str], dialogues: list[tuple[str, str]]) -> float:
    top_len = sum(len(s) for s in stages)
    top_cols = estimate_columns(top_len, TOP_CHARS_PER_COL)
    bottom_cols = 0
    for speaker, text in dialogues:
        body = text[1:-1] if text.startswith("「") and text.endswith("」") else text
        bottom_len = (len(speaker) + len(body)) if body else 0
        bottom_cols = max(bottom_cols, estimate_columns(bottom_len, BOTTOM_CHARS_WITH_STAGE))
    cols = max(top_cols, bottom_cols, 1)
    if len(dialogues) > 1:
        cols += max(0, len(dialogues) - 1)
    return cols * COL_MM + BLOCK_GAP_MM


def estimate_scene_width_mm(label: str) -> float:
    cols = max(1, (len(label) + CHARS_PER_COL_EST - 1) // CHARS_PER_COL_EST)
    return cols * COL_MM + BLOCK_GAP_MM


def _page_width(page: list[tuple[str, float]], scale: float = 1.0) -> float:
    return sum(width * scale for _, width in page)


def _rebalance_orphan_tail(pages: list[list[tuple[str, float]]]) -> list[list[tuple[str, float]]]:
    """最終ページが薄い場合、前ページに収まればブロックを寄せる。"""
    while len(pages) >= 2:
        last = pages[-1]
        if _page_width(last) > ORPHAN_PAGE_MAX_MM:
            break
        prev = pages[-2]
        if _page_width(prev, RELAXED_WIDTH_SCALE) + _page_width(last, RELAXED_WIDTH_SCALE) <= PAGE_PRINTABLE_WIDTH_MM:
            pages[-2] = prev + last
            pages.pop()
            continue
        moved = False
        while last:
            next_w = last[0][1]
            if _page_width(prev, RELAXED_WIDTH_SCALE) + next_w * RELAXED_WIDTH_SCALE <= PAGE_PRINTABLE_WIDTH_MM:
                prev = pages[-2]
                pages[-2] = prev + [last.pop(0)]
                moved = True
            else:
                break
        if not last:
            pages.pop()
        if not moved:
            break
    return pages


def wrap_script_pages(items: list[tuple[str, float]]) -> str:
    """1ページ分の横幅を超える前に改ページし、ブロック途中の切断を防ぐ。"""
    pages: list[list[tuple[str, float]]] = []
    current: list[tuple[str, float]] = []
    current_w = 0.0

    for html, width in items:
        if current and current_w + width > PAGE_USABLE_MM:
            pages.append(current)
            current = []
            current_w = 0.0
        current.append((html, width))
        current_w += width

    if current:
        pages.append(current)

    pages = _rebalance_orphan_tail(pages)

    return "".join(f'<div class="script-page">{"".join(html for html, _ in page)}</div>' for page in pages)


def _cover_body() -> str:
    parts = ['<div class="cover-page"><div class="cover-flow">']
    parts.append('<div class="title">異常な日常の物語<br>最適化された男</div>')
    parts.append('<div class="subtitle">脚本：藤優真</div>')
    parts.append("<h2>登場人物</h2>")
    parts.append('<div class="cast-list">')
    for name, desc, scenes in CAST_ROWS:
        parts.append('<div class="cast-entry">')
        parts.append(f'<div class="cast-name">{name}</div>')
        parts.append(f'<div class="cast-desc">{desc}</div>')
        parts.append(f'<div class="cast-scenes"><span class="cast-label">出番</span>{scenes}</div>')
        parts.append("</div>")
    parts.append("</div></div>")
    return "".join(parts)


def _coalesce_units(units: list[tuple]) -> list[tuple]:
    """同一話者・ト書きなしの連続セリフを1ユニットにまとめる。"""
    merged: list[tuple] = []
    for unit in units:
        if unit[0] == "scene":
            merged.append(unit)
            continue
        _, stages, speaker, text = unit
        if (
            merged
            and merged[-1][0] == "unit"
            and not stages
            and not merged[-1][1]
            and speaker
            and merged[-1][2]
            and speaker == merged[-1][2][0][0]
        ):
            merged[-1][2].append(("", text))
            continue
        merged.append(("unit", stages, [(speaker, text)]))
    return merged


def _collect_script_items() -> list[tuple[str, float]]:
    items: list[tuple[str, float]] = []
    units = split_long_units(normalize_script_blocks(SCRIPT_BLOCKS))
    for unit in _coalesce_units(units):
        if unit[0] == "scene":
            label = unit[1]
            items.append(
                (f'<div class="scene-block"><div class="scene">{label}</div></div>', estimate_scene_width_mm(label))
            )
        else:
            _, stages, dialogues = unit
            html = render_script_block(stages, dialogues)
            items.append((html, estimate_block_width_mm(stages, dialogues)))
    return items


def _script_body() -> str:
    return f'<div class="script-body">{wrap_script_pages(_collect_script_items())}</div>'


def _wrap_document(body: str) -> str:
    return HTML_HEAD.format(css=VERTICAL_CSS) + body + HTML_TAIL


def build_cover_html() -> str:
    return _wrap_document(_cover_body())


def build_script_html() -> str:
    return _wrap_document(_script_body())


def build_html() -> str:
    """プレビュー・整合性検証用（表紙＋本編）。"""
    return _wrap_document(_cover_body() + _script_body())


def html_to_pdf(edge: Path, html_path: Path, pdf_path: Path) -> None:
    url = html_path.resolve().as_uri()
    cmd = [
        str(edge),
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"PDF生成に失敗しました: {pdf_path}")


def merge_pdfs(sources: list[Path], destination: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for source in sources:
        reader = PdfReader(str(source))
        for page in reader.pages:
            writer.add_page(page)
    with destination.open("wb") as fp:
        writer.write(fp)


def build_pdf() -> None:
    errors = verify_text_integrity()
    if errors:
        for msg in errors:
            print(f"WARNING: {msg}", file=sys.stderr)
        raise RuntimeError(f"セリフ欠落を検出: {len(errors)}件")
    edge = find_edge()
    tmp_dir = SCRIPT_DIR / "_pdf_tmp"
    tmp_dir.mkdir(exist_ok=True)
    cover_html = tmp_dir / "cover.html"
    script_html = tmp_dir / "script.html"
    cover_pdf = tmp_dir / "cover.pdf"
    script_pdf = tmp_dir / "script.pdf"
    try:
        cover_html.write_text(build_cover_html(), encoding="utf-8")
        script_html.write_text(build_script_html(), encoding="utf-8")
        html_to_pdf(edge, cover_html, cover_pdf)
        html_to_pdf(edge, script_html, script_pdf)
        merge_pdfs([cover_pdf, script_pdf], OUTPUT)
        print(f"Generated: {OUTPUT} ({OUTPUT.stat().st_size / 1024:.1f} KB)")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    build_pdf()
