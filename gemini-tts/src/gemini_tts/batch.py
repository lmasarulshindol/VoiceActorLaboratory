"""マニフェストから一括 TTS する（APIキー必須）."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .audio import save_wav
from .client import GeminiTTSClient
from .project import load_manifest


def _is_rate_limit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or ("rate" in msg and "limit" in msg)


def synthesize_manifest(
    manifest: dict[str, Any],
    project_dir: Path,
    client: GeminiTTSClient,
    *,
    kinds: set[str] | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    delay_sec: float = 6.5,
    max_retries: int = 4,
    on_item: Callable[[dict[str, Any], str], None] | None = None,
) -> dict[str, Any]:
    """manifest の tts=True 項目を順に合成する.

    Args:
        kinds: 指定時はその kind のみ（例: {"dialogue","narration"}）
        dry_run: True なら API を呼ばず計画だけ返す
        delay_sec: リクエスト間隔（無料枠はモデルあたり約10req/分）
    """
    results = {"ok": [], "skipped": [], "errors": [], "planned": []}
    allow = kinds

    for item in manifest.get("items", []):
        if not item.get("tts"):
            results["skipped"].append({"id": item.get("id"), "reason": "tts=false"})
            continue
        kind = item.get("kind")
        if allow is not None and kind not in allow:
            results["skipped"].append({"id": item.get("id"), "reason": f"kind={kind}"})
            continue

        spoken = (item.get("spoken_text") or "").strip()
        if not spoken:
            results["skipped"].append({"id": item.get("id"), "reason": "empty"})
            continue

        rel = item.get("output") or f"audio/{item['id']}.wav"
        out_path = project_dir / rel
        if skip_existing and out_path.is_file() and out_path.stat().st_size > 0:
            results["skipped"].append({"id": item.get("id"), "reason": "exists", "path": str(out_path)})
            continue

        plan = {
            "id": item.get("id"),
            "voice": item.get("voice"),
            "style": item.get("style"),
            "path": str(out_path),
            "chars": len(spoken),
        }
        results["planned"].append(plan)
        if on_item:
            on_item(item, "plan" if dry_run else "start")

        if dry_run:
            continue

        last_exc: BaseException | None = None
        for attempt in range(max_retries + 1):
            try:
                result = client.synthesize(
                    spoken,
                    voice=item.get("voice") or "Kore",
                    style=item.get("style"),
                )
                save_wav(out_path, result.audio_wav, sample_rate=client.sample_rate)
                results["ok"].append(
                    {"id": item.get("id"), "path": str(out_path), "bytes": len(result.audio_wav)}
                )
                if on_item:
                    on_item(item, "ok")
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001 - バッチ継続のため
                last_exc = exc
                if _is_rate_limit_error(exc) and attempt < max_retries:
                    wait = 30.0 * (attempt + 1)
                    if on_item:
                        on_item(item, f"retry_wait_{int(wait)}s")
                    time.sleep(wait)
                    continue
                break

        if last_exc is not None:
            results["errors"].append({"id": item.get("id"), "error": str(last_exc)})
            if on_item:
                on_item(item, "error")

        if delay_sec > 0:
            time.sleep(delay_sec)

    return results


def synthesize_project(
    project_dir: Path,
    client: GeminiTTSClient,
    **kwargs: Any,
) -> dict[str, Any]:
    manifest_path = project_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json がありません: {manifest_path}")
    manifest = load_manifest(manifest_path)
    return synthesize_manifest(manifest, project_dir, client, **kwargs)
