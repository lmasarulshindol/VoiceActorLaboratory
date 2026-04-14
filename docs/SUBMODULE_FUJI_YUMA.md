# fuji-yuma-master-assets サブモジュール

## 概要

`VoiceActorLaboratory` のサブモジュールとして `fuji-yuma-master-assets` を追加しています。

- **リポジトリ**: https://github.com/lmasarulshindol/fuji-yuma-master-assets
- **配置場所**: `VoiceActorLaboratory/fuji-yuma-master-assets/`

## サブモジュール追加が完了している場合

以下で状態を確認できます。

```powershell
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
cd "c:\Users\MasaruShindo\work2\001_声優・音声\VoiceActorLaboratory"
git submodule status
```

## 初回クローン時（他マシン・別クローンで使う場合）

親リポジトリをクローンしたあと、サブモジュールを取得するには:

```powershell
cd "c:\Users\MasaruShindo\work2\001_声優・音声\VoiceActorLaboratory"
git submodule update --init --recursive
```

## 追加が途中で止まった場合のやり直し

`git submodule add` がタイムアウトなどで完了しなかった場合は、以下でやり直せます。

```powershell
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
cd "c:\Users\MasaruShindo\work2\001_声優・音声\VoiceActorLaboratory"

# 不完全なサブモジュールフォルダを削除
Remove-Item -Recurse -Force .\fuji-yuma-master-assets -ErrorAction SilentlyContinue

# サブモジュールを追加（クローンに時間がかかることがあります）
git submodule add https://github.com/lmasarulshindol/fuji-yuma-master-assets.git fuji-yuma-master-assets

# コミット
git add .gitmodules fuji-yuma-master-assets
git commit -m "Add fuji-yuma-master-assets as submodule"
```

## サブモジュールの更新

`fuji-yuma-master-assets` の最新を取りたい場合:

```powershell
cd "c:\Users\MasaruShindo\work2\001_声優・音声\VoiceActorLaboratory\fuji-yuma-master-assets"
git pull origin main
cd ..
git add fuji-yuma-master-assets
git commit -m "Update fuji-yuma-master-assets submodule"
```
