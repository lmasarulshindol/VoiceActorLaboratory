"""help_content のテスト。"""

from __future__ import annotations

from stream_soundboard import help_content


class TestHelpContent:
    def test_トピックが揃っている(self):
        labels = [t[0] for t in help_content.HELP_TOPICS]
        assert "初期設定（VB-CABLE）" in labels
        assert "操作方法" in labels
        assert "トラブルシューティング" in labels
        assert "このアプリについて" in labels

    def test_初期設定にVB_CABLE手順がある(self):
        assert "VB-CABLE" in help_content.SETUP_GUIDE
        assert "CABLE Input" in help_content.SETUP_GUIDE
        assert "CABLE Output" in help_content.SETUP_GUIDE
        assert "Discord" in help_content.SETUP_GUIDE

    def test_操作方法に右クリックがある(self):
        assert "右クリック" in help_content.HOW_TO_USE
        assert "左クリック" in help_content.HOW_TO_USE

    def test_URLがhttps(self):
        assert help_content.VB_CABLE_URL.startswith("https://")
