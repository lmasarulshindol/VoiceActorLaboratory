"""Gemini TTS CLI.

使い方:
  py -3 -m gemini_tts list-voices
  py -3 -m gemini_tts synthesize "こんにちは" -o output/hello.wav
  py -3 -m gemini_tts parse-script 台本.md -o projects/foo
  py -3 -m gemini_tts synthesize-project projects/foo --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from gemini_tts.audio import save_wav
from gemini_tts.batch import synthesize_manifest, synthesize_project
from gemini_tts.client import GeminiTTSClient, SpeakerVoice
from gemini_tts.config import load_config
from gemini_tts.project import create_project_from_script, load_manifest
from gemini_tts.voices import list_voices


def _package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_env_path() -> Path:
    return _package_root() / ".env"


def _default_config_path() -> Path | None:
    path = _package_root() / "config.yaml"
    return path if path.is_file() else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gemini-tts",
        description="Google Gemini TTS でテキストから音声を生成する",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="設定 YAML（省略時は ./config.yaml があれば使用）",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=None,
        help=".env のパス（省略時はパッケージ直下の .env）",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-voices", help="プリビルトボイス一覧を表示")
    p_list.set_defaults(func=cmd_list_voices)

    p_syn = sub.add_parser("synthesize", help="テキストから音声を生成")
    p_syn.add_argument("text", nargs="?", default=None, help="読み上げテキスト")
    p_syn.add_argument("-f", "--file", type=Path, help="テキストファイル（UTF-8）")
    p_syn.add_argument("-o", "--output", type=Path, help="出力 WAV パス")
    p_syn.add_argument("--voice", help="ボイス名（例: Kore, Aoede）")
    p_syn.add_argument("--model", help="モデル名（例: gemini-3.8-flash-tts）")
    p_syn.add_argument("--style", help="話し方・演技指示")
    p_syn.add_argument("--language", dest="language_code", help="言語コード（例: ja-JP）")
    p_syn.add_argument(
        "--speaker",
        action="append",
        metavar="NAME:VOICE",
        help="マルチスピーカー（例: --speaker Alice:Kore --speaker Bob:Puck）",
    )
    p_syn.set_defaults(func=cmd_synthesize)

    p_parse = sub.add_parser(
        "parse-script",
        help="台本MDからプロジェクト（manifest等）を生成（API不要）",
    )
    p_parse.add_argument("script", type=Path, help="台本 Markdown パス")
    p_parse.add_argument(
        "-o",
        "--project-dir",
        type=Path,
        required=True,
        help="出力プロジェクトディレクトリ",
    )
    p_parse.add_argument("--title", help="プロジェクトタイトル")
    p_parse.set_defaults(func=cmd_parse_script)

    p_proj = sub.add_parser(
        "synthesize-project",
        help="manifest.json から一括音声生成（APIキー必要）",
    )
    p_proj.add_argument("project_dir", type=Path, help="プロジェクトディレクトリ")
    p_proj.add_argument(
        "--dry-run",
        action="store_true",
        help="APIを呼ばず生成計画だけ表示",
    )
    p_proj.add_argument(
        "--kinds",
        default="dialogue,narration,caption",
        help="対象kind（カンマ区切り）。例: dialogue,narration",
    )
    p_proj.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="既存WAVがあっても再生成",
    )
    p_proj.add_argument("--model", help="モデル上書き")
    p_proj.set_defaults(func=cmd_synthesize_project)

    return parser


def cmd_list_voices(_args: argparse.Namespace) -> int:
    print(f"{'Voice':<18} Description")
    print("-" * 40)
    for v in list_voices():
        print(f"{v.name:<18} {v.description}")
    return 0


def _parse_speakers(specs: list[str] | None) -> list[SpeakerVoice] | None:
    if not specs:
        return None
    result: list[SpeakerVoice] = []
    for raw in specs:
        if ":" not in raw:
            raise ValueError(f"--speaker は NAME:VOICE 形式です: {raw!r}")
        name, voice = raw.split(":", 1)
        name, voice = name.strip(), voice.strip()
        if not name or not voice:
            raise ValueError(f"--speaker は NAME:VOICE 形式です: {raw!r}")
        result.append(SpeakerVoice(speaker=name, voice=voice))
    return result


def _read_text(args: argparse.Namespace) -> str:
    if args.file is not None:
        return args.file.read_text(encoding="utf-8")
    if args.text == "-":
        return sys.stdin.read()
    if args.text:
        return args.text
    raise ValueError(
        "テキストを引数・-f で指定してください（標準入力はテキストに - を指定）"
    )


def _default_output_path(output_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"tts_{stamp}.wav"


def cmd_synthesize(args: argparse.Namespace) -> int:
    config_path = args.config if args.config is not None else _default_config_path()
    env_path = args.env if args.env is not None else _default_env_path()

    overrides = {
        "model": args.model,
        "voice": args.voice,
        "style": args.style,
        "language_code": args.language_code,
    }
    cfg = load_config(config_path=config_path, env_path=env_path, overrides=overrides)
    api_key = cfg.require_api_key()

    text = _read_text(args)
    speakers = _parse_speakers(args.speaker)

    client = GeminiTTSClient(
        api_key,
        model=cfg.model,
        sample_rate=cfg.sample_rate,
    )
    result = client.synthesize(
        text,
        voice=cfg.voice,
        style=cfg.style,
        language_code=cfg.language_code,
        speakers=speakers,
    )

    out = args.output or _default_output_path(cfg.output_dir)
    if not out.is_absolute():
        out = _package_root() / out

    saved = save_wav(out, result.audio_wav, sample_rate=cfg.sample_rate)
    print(f"saved: {saved}")
    print(f"model: {result.model}")
    if result.mime_type:
        print(f"mime:  {result.mime_type}")
    print(f"bytes: {len(result.audio_wav)}")
    return 0


def cmd_parse_script(args: argparse.Namespace) -> int:
    script = args.script
    if not script.is_file():
        raise FileNotFoundError(f"台本が見つかりません: {script}")
    project_dir = args.project_dir
    if not project_dir.is_absolute():
        project_dir = _package_root() / project_dir

    manifest = create_project_from_script(
        script,
        project_dir,
        title=args.title,
    )
    summary = manifest["summary"]
    print(f"project: {project_dir}")
    print(f"title:   {manifest['title']}")
    print(f"total:   {summary['total']}")
    print(f"tts:     {summary['tts_targets']}")
    print(f"kinds:   {summary['by_kind']}")
    print(f"speakers:{summary['speakers']}")
    print("files:   manifest.json / voice_map.yaml / LINES.md / README.md")
    return 0


def cmd_synthesize_project(args: argparse.Namespace) -> int:
    project_dir = args.project_dir
    if not project_dir.is_absolute():
        project_dir = _package_root() / project_dir
    if not project_dir.is_dir():
        raise FileNotFoundError(f"プロジェクトがありません: {project_dir}")

    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    if args.dry_run:
        manifest = load_manifest(project_dir / "manifest.json")

        class _NoClient:
            sample_rate = 24000

        results = synthesize_manifest(
            manifest,
            project_dir,
            client=_NoClient(),  # type: ignore[arg-type]
            kinds=kinds,
            dry_run=True,
            skip_existing=not args.no_skip_existing,
        )
        print(f"planned: {len(results['planned'])}")
        print(f"skipped: {len(results['skipped'])}")
        for p in results["planned"][:20]:
            print(f"  - {p['id']} voice={p['voice']} chars={p['chars']} -> {p['path']}")
        if len(results["planned"]) > 20:
            print(f"  ... and {len(results['planned']) - 20} more")
        return 0

    config_path = args.config if args.config is not None else _default_config_path()
    env_path = args.env if args.env is not None else _default_env_path()
    cfg = load_config(
        config_path=config_path,
        env_path=env_path,
        overrides={"model": args.model},
    )
    api_key = cfg.require_api_key()
    client = GeminiTTSClient(api_key, model=cfg.model, sample_rate=cfg.sample_rate)

    def _log(item: dict, status: str) -> None:
        print(f"[{status}] {item.get('id')} {item.get('resolved_speaker') or item.get('kind')}")

    results = synthesize_project(
        project_dir,
        client,
        kinds=kinds,
        dry_run=False,
        skip_existing=not args.no_skip_existing,
        on_item=_log,
    )
    print(
        f"done: ok={len(results['ok'])} skipped={len(results['skipped'])} "
        f"errors={len(results['errors'])}"
    )
    for err in results["errors"]:
        print(f"  error {err['id']}: {err['error']}", file=sys.stderr)
    return 1 if results["errors"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
